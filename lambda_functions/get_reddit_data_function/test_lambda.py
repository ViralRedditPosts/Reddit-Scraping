from datetime import datetime, UTC, timedelta
import pytest
import reddit_utils as ru
import praw
import table_definition
from collections import namedtuple
import boto3
import os
import viral_reddit_posts_utils.configUtils as cu
from moto import mock_dynamodb
from unittest.mock import patch, Mock
from dataclasses import dataclass


IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
HIT_REDDIT = False  # set this to true if you want to test on realtime reddit data
PATH_OF_THIS_FILE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope='module')
def reddit() -> praw.Reddit:
    if not HIT_REDDIT:  # just load the fake config
        cfg_file = os.path.join(PATH_OF_THIS_FILE, "../../example_reddit.cfg")
    else:  # Try to get the real config file
        try:
            cfg_file = cu.findConfig()
        except RuntimeError as e:
            print(e)
            cfg_file = os.path.join(PATH_OF_THIS_FILE, "../../example_reddit.cfg")
    print(f"{cfg_file=}")
    cfg = cu.parseConfig(cfg_file)
    reddit_cfg = cfg['reddit_api']
    return praw.Reddit(
        client_id=f"{reddit_cfg['CLIENTID']}",
        client_secret=f"{reddit_cfg['CLIENTSECRET']}",
        password=f"{reddit_cfg['PASSWORD']}",
        user_agent=f"Post Extraction (by u/{reddit_cfg['USERNAME']})",
        username=f"{reddit_cfg['USERNAME']}",
    )


@dataclass
class SubredditSample():
    subscribers = 10000000
    accounts_active = 10000

    @dataclass
    class SampleRisingSubmission():
        # set created time 15 min before now so it gets filtered into selected data
        created_utc = int((datetime.now(UTC).replace(tzinfo=UTC, microsecond=0) - timedelta(minutes=15)).timestamp())
        stickied = False
        id = '1c3dwli'
        title = 'My son and my ferret. 😂'
        score = 28
        num_comments = 1
        upvote_ratio = 0.86
        gildings = {}

    @staticmethod
    def rising_generator():
        yield SubredditSample.SampleRisingSubmission

    @staticmethod
    def rising(limit):
        generator = SubredditSample.rising_generator()
        return generator


@patch(target="praw.models.helpers.SubredditHelper.__call__", return_value = SubredditSample)
def test_get_reddit_data(
        mock_subreddit:Mock,
        reddit: praw.Reddit
):
  subreddit = "pics"
  data_collected = ru.get_reddit_data(
    reddit,
    subreddit,
    top_n=25,
    view='rising',
    schema=table_definition.schema,
    time_filter=None,
    verbose=True
  )
  if not HIT_REDDIT:  # fake data
    row = data_collected[0]
    assert row.subscribers == 10000000
    assert row.activeUsers == 10000
    assert row.title == 'My son and my ferret. 😂'
    assert row.postId == '1c3dwli'


@pytest.fixture(scope='module')
def duplicated_data():
  schema = table_definition.schema
  columns = list(schema.keys())
  Row = namedtuple(typename="Row", field_names=columns)
  # these are identical examples except one has a later loadTSUTC
  return [
    Row(subscribers=10000000, activeUsers=10000,
        loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqz',
        subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
        timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0),
    Row(subscribers=10000000, activeUsers=10000,
        loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:06:44', postId='133fkqz',
        subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
        timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0)
  ]


def test_deduplicate_reddit_data(duplicated_data):
  new_data = ru.deduplicate_reddit_data(duplicated_data)
  assert len(new_data) == 1
  print("test_deduplicateRedditData complete")


@mock_dynamodb
class TestBatchWriter:
  def class_set_up(self):
    """
    If we left this at top level of the class then it won't be skipped by `skip` and `skipif`
    furthermore we can't have __init__ in a Test Class, so this is called prior to each test
    :return:
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    # create table and write to sample data
    table_name = 'rising'
    td = table_definition.getTableDefinition(tableName=table_name)
    self.test_table = dynamodb.create_table(**td)
    self.schema = table_definition.schema
    self.columns = self.schema.keys()
    self.Row = namedtuple(typename="Row", field_names=self.columns)

  @pytest.mark.xfail(reason="BatchWriter fails on duplicate keys. This might xpass, possibly a fault in mock object.")
  def test_duplicate_data(self):
    self.class_set_up()
    testTable = self.test_table
    schema = self.schema
    Row=self.Row

    data = [
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqz',
         subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
         timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0),
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqz',
          subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
          timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0)
     ]
    ru.batch_writer(table=testTable, data=data, schema=schema)
    print("duplicateDataTester test complete")

  def test_unique_data(self):
    self.class_set_up()
    test_table = self.test_table
    schema = self.schema
    Row = self.Row

    data = [
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqz',
          subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
          timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0),
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fqj7',
          subreddit='pics', title='A piece of wood sticking up in front of a fire.', createdTSUTC='2023-04-30 04:29:23',
          timeElapsedMin=34, score=0, numComments=0, upvoteRatio=0.4, numGildings=0)
    ]
    ru.batch_writer(table=test_table, data=data, schema=schema)
    print("uniqueDataTester test complete")

  def test_diff_primary_index_same_second_index(self):
    self.class_set_up()
    test_table = self.test_table
    schema = self.schema
    Row = self.Row

    data = [
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqz',
          subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
          timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0),
      Row(subscribers=10000000, activeUsers=10000,
          loadDateUTC='2023-04-30', loadTimeUTC='05:03:44', loadTSUTC='2023-04-30 05:03:44', postId='133fkqy',
          subreddit='pics', title='Magnolia tree blooming in my friends yard', createdTSUTC='2023-04-30 04:19:43',
          timeElapsedMin=44, score=3, numComments=0, upvoteRatio=1.0, numGildings=0)
    ]

    ru.batch_writer(table=test_table, data=data, schema=schema)
    print("diffPrimaryIndexSameSecondIndexTester test complete")
