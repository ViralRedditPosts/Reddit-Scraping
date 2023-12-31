from datetime import datetime
from collections import namedtuple
import tableDefinition
import json
from decimal import Decimal
import pickle


def saveTestReddit(reddit, filename):
  pickle.dump(reddit, open(filename, 'wb'))


def getRedditData(reddit, subreddit, topN=25, view='rising', schema=tableDefinition.schema, time_filter=None, verbose=False):
  """
  Uses PRAW to get data from reddit using defined parameters. Returns data in a list of row based data.

  :param reddit: PRAW reddit object
  :param subreddit: subreddit name
  :param topN: Number of posts to return
  :param view: view to look at the subreddit. rising, top, hot
  :param schema: schema that describes the data. Dynamo is technically schema-less
  :param time_filter: range of time to look at the data. all, day, hour, month, week, year
  :param verbose: if True then prints more information
  :return: list[Row[schema]], Row is a namedtuple defined by the schema
  """
  assert topN <= 25  # some, like rising, cap out at 25 and this also is to limit data you're working with
  assert view in {'rising', 'top' , 'hot'}
  topN += 2  # increment by 2 because of sticky posts
  if view == 'top':
    assert time_filter in {"all", "day", "hour", "month", "week", "year"}
  subredditObject = reddit.subreddit(subreddit)
  if view == 'rising':
    topNposts = subredditObject.rising(limit=topN)
  elif view == 'hot':
    topNposts = subredditObject.hot(limit=topN)
  elif view == 'top':
    topNposts = subredditObject.top(time_filter=time_filter, limit=topN)

  now = datetime.utcnow().replace(tzinfo=None, microsecond=0)
  columns = schema.keys()
  Row = namedtuple("Row", columns)
  dataCollected = []
  subscribers = subredditObject.subscribers
  activeUsers = subredditObject.accounts_active
  print(f'\tSubscribers: {subscribers}\n\tActive users: {activeUsers}')
  for submission in topNposts:
    if submission.stickied:
      continue  # skip stickied posts
    createdTSUTC = datetime.utcfromtimestamp(submission.created_utc)
    timeSincePost = now - createdTSUTC
    timeElapsedMin = timeSincePost.seconds // 60
    timeElapsedDays = timeSincePost.days
    if view=='rising' and (timeElapsedMin > 60 or timeElapsedDays>0):  # sometime rising has some data that's already older than an hour or day, we don't want that
      continue
    postId = submission.id
    title = submission.title
    score = submission.score
    numComments = submission.num_comments
    upvoteRatio = submission.upvote_ratio
    gildings = submission.gildings
    numGildings = sum(gildings.values())
    row = Row(
      postId=postId, subreddit=subreddit, subscribers=subscribers, activeUsers=activeUsers,
      title=title, createdTSUTC=str(createdTSUTC),
      timeElapsedMin=timeElapsedMin, score=score, numComments=numComments,
      upvoteRatio=upvoteRatio, numGildings=numGildings,
      loadTSUTC=str(now), loadDateUTC=str(now.date()), loadTimeUTC=str(now.time()))
    dataCollected.append(row)
    if verbose:
      print(row)
      print()
  return dataCollected[:topN-2]


def deduplicateRedditData(data):
  """
  Deduplicates the reddit data. Sometimes there are duplicate keys which throws an error
  when writing to dynamo. It is unclear why this happens but I suspect it is an issue with PRAW.

  :param data: list[Row[schema]]
  :return: deduplicated data
  """
  postIds = set()
  newData = []
  # there really shouldn't be more than 1 loadTSUTC for a postId since that is generated
  # on our side, but I wanted to handle that since it is part of the key
  data = sorted(data, key=lambda x: x.loadTSUTC)[::-1]
  for d in data:
    if d.postId not in postIds:
      postIds.add(d.postId)
      newData.append(d)
  return newData


def getTable(tableName, dynamodb_resource):
    table = dynamodb_resource.Table(tableName)

    # Print out some data about the table.
    print(f"Item count in table: {table.item_count}")  # this only updates every 6 hours
    return table


def batchWriter(table, data, schema):
  """
  https://boto3.amazonaws.com/v1/documentation/api/latest/guide/dynamodb.html#batch-writing
  I didn't bother with dealing with duplicates because shouldn't be a problem with this type of data
  no built in way to get responses with batch_writer https://peppydays.medium.com/getting-response-of-aws-dynamodb-batchwriter-request-2aa3f81019fa

  :param table: boto3 table object
  :param data: list[Row[schema]]
  :param schema: OrderedDict containing the dynamodb schema (dynamo technically schema-less)
  :return: None
  """
  columns = schema.keys()
  with table.batch_writer() as batch:
    for i in range(len(data)):  # for each row obtained
      batch.put_item(
        Item = json.loads(json.dumps({k:getattr(data[i], k) for k in columns}), parse_float=Decimal) # helps with parsing float to Decimal
      )