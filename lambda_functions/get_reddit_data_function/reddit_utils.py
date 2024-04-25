from datetime import datetime, UTC
from collections import namedtuple, OrderedDict
import table_definition
import json
from decimal import Decimal
import pickle
from praw import Reddit


def get_reddit_data(
        reddit: Reddit,
        subreddit: str,
        top_n: int = 25,
        view: str = 'rising',
        schema: OrderedDict = table_definition.schema,
        time_filter: str | None = None,
        verbose: bool = False
):
  """
  Uses PRAW to get data from reddit using defined parameters. Returns data in a list of row based data.

  :param reddit: PRAW reddit object
  :param subreddit: subreddit name
  :param top_n: Number of posts to return
  :param view: view to look at the subreddit. rising, top, hot
  :param schema: schema that describes the data. Dynamo is technically schema-less
  :param time_filter: range of time to look at the data. all, day, hour, month, week, year
  :param verbose: if True then prints more information
  :return: list[Row[schema]], Row is a namedtuple defined by the schema
  """
  assert top_n <= 25  # some, like rising, cap out at 25 and this also is to limit data you're working with
  assert view in {'rising', 'top' , 'hot'}
  top_n += 2  # increment by 2 because of sticky posts
  if view == 'top':
    assert time_filter in {"all", "day", "hour", "month", "week", "year"}
  subreddit_object = reddit.subreddit(subreddit)
  top_n_posts = None
  if view == 'rising':
    top_n_posts = subreddit_object.rising(limit=top_n)
  elif view == 'hot':
    top_n_posts = subreddit_object.hot(limit=top_n)
  elif view == 'top':
    top_n_posts = subreddit_object.top(time_filter=time_filter, limit=top_n)

  now = datetime.now(UTC).replace(tzinfo=UTC, microsecond=0)
  columns = list(schema.keys())
  Row = namedtuple(typename="Row", field_names=columns)
  data_collected = []
  subscribers = subreddit_object.subscribers
  active_users = subreddit_object.accounts_active
  print(f'\tSubscribers: {subscribers}\n\tActive users: {active_users}')

  for submission in top_n_posts:
    if submission.stickied:
      continue  # skip stickied posts
    createdTSUTC = datetime.fromtimestamp(submission.created_utc, UTC)
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
      postId=postId, subreddit=subreddit, subscribers=subscribers, activeUsers=active_users,
      title=title, createdTSUTC=str(createdTSUTC),
      timeElapsedMin=timeElapsedMin, score=score, numComments=numComments,
      upvoteRatio=upvoteRatio, numGildings=numGildings,
      loadTSUTC=str(now), loadDateUTC=str(now.date()), loadTimeUTC=str(now.time()))
    data_collected.append(row)
    if verbose:
      print(row)
      print()
  return data_collected


def deduplicate_reddit_data(data):
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


def get_table(tableName, dynamodb_resource):
    table = dynamodb_resource.Table(tableName)

    # Print out some data about the table.
    print(f"Item count in table: {table.item_count}")  # this only updates every 6 hours
    return table


def batch_writer(table, data, schema):
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