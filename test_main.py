import unittest
from unittest.mock import patch, MagicMock
from main import main, fetch_messages_for_date
from slack_sdk.errors import SlackApiError
import mongomock
import os
from datetime import datetime

class TestMain(unittest.TestCase):

    def setUp(self):
        """テストの前に呼ばれるセットアップメソッド"""
        self.mongo_client = mongomock.MongoClient()
        self.db = self.mongo_client.taco

    def tearDown(self):
        """テストの後に呼ばれるクリーンアップメソッド"""
        self.mongo_client.close()

    @patch('main.WebClient')
    @patch('main.MongoClient')
    def test_main_saves_to_mongodb(self, MockMongoClient, MockWebClient):
        """
        main関数がMongoDBにデータを正しく保存することをテストする
        """
        # モックの設定
        MockMongoClient.return_value = self.mongo_client
        mock_slack_client = MockWebClient.return_value
        mock_slack_client.conversations_history.return_value = {
            "messages": [
                {"text": "Hello from channel 1", "ts": "1", "user": "U1"}
            ]
        }
        mock_slack_client.conversations_replies.return_value = {"messages": []}
        mock_slack_client.users_info.return_value = {"user": {"real_name": "Test User"}}

        # 環境変数の設定
        os.environ['SLACK_API_TOKEN'] = 'test_token'
        os.environ['SLACK_CHANNEL_IDS'] = 'C123,C456'
        os.environ['MONGO_URI'] = 'mongodb://localhost:27017/'
        os.environ['MONGO_DB_NAME'] = 'taco'

        # テスト対象の関数を実行
        today_str = datetime.today().strftime('%Y-%m-%d')
        main(today_str)

        # 検証
        collection1 = self.db['raw_messages_C123']
        self.assertEqual(collection1.count_documents({}), 1)
        doc1 = collection1.find_one()
        self.assertEqual(doc1['date'], today_str)
        self.assertEqual(len(doc1['messages']), 1)
        self.assertEqual(doc1['messages'][0]['text'], "Hello from channel 1")

        collection2 = self.db['raw_messages_C456']
        self.assertEqual(collection2.count_documents({}), 1)

    @patch('main.WebClient')
    def test_fetch_messages_for_date_error(self, MockWebClient):
        """
        Slack APIエラー発生時のメッセージ取得テスト
        """
        mock_client = MockWebClient.return_value
        mock_client.conversations_history.side_effect = SlackApiError("An error occurred", MagicMock())
        
        result = fetch_messages_for_date(mock_client, "C12345", datetime.today())
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()