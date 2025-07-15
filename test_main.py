import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import json
from datetime import datetime
import sys

from slack_sdk.errors import SlackApiError

# テスト対象のスクリプトをインポート
from main import main, fetch_messages_for_date

class TestMain(unittest.TestCase):

    @patch('main.WebClient')
    def test_fetch_messages_for_date_success(self, MockWebClient):
        """
        fetch_messages_for_dateが正常にメッセージを取得するかのテスト
        """
        # モックの設定
        mock_client = MockWebClient.return_value
        mock_client.conversations_history.return_value = {
            "messages": [{"text": "hello", "ts": "1", "user": "U1"}]
        }
        mock_client.conversations_replies.return_value = {"messages": []}
        mock_client.users_info.return_value = {"user": {"real_name": "Test User"}}

        # 実行
        target_date = datetime(2025, 7, 15).date()
        messages = fetch_messages_for_date(mock_client, "C12345", target_date)

        # 検証
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['text'], 'hello')
        self.assertEqual(messages[0]['user_name'], 'Test User')
        mock_client.conversations_history.assert_called_once()

    @patch('main.WebClient')
    def test_fetch_messages_for_date_api_error(self, MockWebClient):
        """
        Slack APIエラー時にfetch_messages_for_dateが空のリストを返すかのテスト
        """
        # モックの設定
        mock_client = MockWebClient.return_value
        mock_client.conversations_history.side_effect = SlackApiError("API Error", MagicMock())

        # 実行
        target_date = datetime(2025, 7, 15).date()
        messages = fetch_messages_for_date(mock_client, "C12345", target_date)

        # 検証
        self.assertEqual(messages, [])

    @patch.dict(os.environ, {
        "SLACK_API_TOKEN": "test_token",
        "SLACK_CHANNEL_IDS": "C1, C2"
    })
    @patch('main.fetch_messages_for_date')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_main_multi_channel_support(self, mock_makedirs, mock_file, mock_fetch):
        """
        main関数が複数チャンネルに対応しているかのテスト
        """
        # モックの設定
        mock_fetch.return_value = [{"text": "message"}]
        target_date_str = "2025-07-15"

        # 実行
        main(target_date_str)

        # 検証
        self.assertEqual(mock_fetch.call_count, 2)
        mock_fetch.assert_any_call(unittest.mock.ANY, "C1", datetime(2025, 7, 15).date())
        mock_fetch.assert_any_call(unittest.mock.ANY, "C2", datetime(2025, 7, 15).date())

        self.assertEqual(mock_file.call_count, 2)
        expected_path1 = os.path.join("reports/raw", "raw_messages_C1_2025-07-15.json")
        expected_path2 = os.path.join("reports/raw", "raw_messages_C2_2025-07-15.json")
        mock_file.assert_any_call(expected_path1, "w", encoding="utf-8")
        mock_file.assert_any_call(expected_path2, "w", encoding="utf-8")

    @patch.dict(os.environ, {})
    @patch('sys.stderr', new_callable=unittest.mock.MagicMock)
    def test_main_no_env_vars(self, mock_stderr):
        """
        環境変数がない場合にmain関数がエラー終了するかのテスト
        """
        main()
        self.assertTrue(mock_stderr.write.called)

if __name__ == '__main__':
    unittest.main()