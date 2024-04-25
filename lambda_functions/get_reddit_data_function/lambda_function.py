import reddit_utils as ru
import viral_reddit_posts_utils.configUtils as cu
import table_definition
import praw
import boto3
import os


dynamodb_resource = boto3.resource('dynamodb')


def lambda_handler(event, context):
  # Initializations
  subreddits = ["pics", "gaming", "worldnews", "news", "aww", "funny", "todayilearned", "movies"]

  # cfg_file = cu.findConfig()
  cfg_file = "s3://"+os.environ['AWS_BUCKET']+"/reddit.cfg" # ie 's3://data-kennethmyers/reddit.cfg'
  cfg = cu.parseConfig(cfg_file)

  CLIENTID = cfg['reddit_api']['CLIENTID']
  CLIENTSECRET = cfg['reddit_api']['CLIENTSECRET']
  PASSWORD = cfg['reddit_api']['PASSWORD']
  USERNAME = cfg['reddit_api']['USERNAME']

  reddit = praw.Reddit(
    client_id=f"{CLIENTID}",
    client_secret=f"{CLIENTSECRET}",
    password=f"{PASSWORD}",
    user_agent=f"Post Extraction (by u/{USERNAME})",
    username=f"{USERNAME}",
  )

  for subreddit in subreddits:
    print(f"Gathering data for {subreddit}")
    # Get Rising Reddit data
    print("\tGetting Rising Data")
    schema = table_definition.schema
    topN = 25
    view = 'rising'
    risingData = ru.get_reddit_data(reddit=reddit, subreddit=subreddit, view=view, schema=schema, top_n=topN)
    risingData = ru.deduplicate_reddit_data(risingData)

    # Push to DynamoDB
    tableName = f"{view}-{os.environ['ENV']}"
    risingTable = ru.get_table(tableName, dynamodb_resource)
    ru.batch_writer(risingTable, risingData, schema)

    # Get Hot Reddit data
    print("\tGetting Hot Data")
    schema = table_definition.schema
    topN = 3
    view = 'hot'
    hotData = ru.get_reddit_data(reddit=reddit, subreddit=subreddit, view=view, schema=schema, top_n=topN)
    hotData = ru.deduplicate_reddit_data(hotData)

    # Push to DynamoDB
    tableName = f"{view}-{os.environ['ENV']}"
    hotTable = ru.get_table(tableName, dynamodb_resource)
    ru.batch_writer(hotTable, hotData, schema)

  return 200
