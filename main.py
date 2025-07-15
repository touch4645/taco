import os
import json
from datetime import datetime, time, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import sys
from pymongo import MongoClient

def fetch_messages_for_date(client: WebClient, channel_id: str, target_date: datetime) -> list:
    """
    指定されたSlackチャンネルから指定された日付のメッセージとスレッドを取得します。
    """
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)
    try:
        result = client.conversations_history(
            channel=channel_id,
            oldest=str(day_start.timestamp()),
            latest=str(day_end.timestamp())
        )
        messages = result.get("messages", [])

        threaded_messages = []
        for msg in messages:
            if "thread_ts" in msg:
                thread_replies = client.conversations_replies(
                    channel=channel_id,
                    ts=msg["thread_ts"]
                )
                threaded_messages.extend(thread_replies.get("messages", []))
        all_messages = {msg['ts']: msg for msg in messages + threaded_messages}.values()

        users_cache = {}
        for msg in all_messages:
            user_id = msg.get("user")
            if user_id and user_id not in users_cache:
                try:
                    user_info = client.users_info(user=user_id)
                    users_cache[user_id] = user_info["user"]["real_name"] or user_info["user"]["name"]
                except SlackApiError:
                    users_cache[user_id] = user_id
            
            if user_id in users_cache:
                msg["user_name"] = users_cache[user_id]

        return list(all_messages)
    except SlackApiError as e:
        print(f"Error fetching messages for {target_date.strftime('%Y-%m-%d')}: {e}")
        return []

def main(target_date_str: str = None):
    """
    メイン処理：Slackからメッセージを取得し、MongoDBに保存する
    """
    load_dotenv()
    slack_token = os.environ.get("SLACK_API_TOKEN")
    channel_ids_str = os.environ.get("SLACK_CHANNEL_IDS")
    mongo_uri = os.environ.get("MONGO_URI")
    mongo_db_name = os.environ.get("MONGO_DB_NAME")

    if not all([slack_token, channel_ids_str, mongo_uri, mongo_db_name]):
        print("Error: SLACK_API_TOKEN, SLACK_CHANNEL_IDS, MONGO_URI, and MONGO_DB_NAME must be set in .env file.", file=sys.stderr)
        return

    channel_ids = [c.strip() for c in channel_ids_str.split(',')]
    slack_client = WebClient(token=slack_token)
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client[mongo_db_name]

    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Error: Invalid date format. Please use YYYY-MM-DD. Got: {target_date_str}", file=sys.stderr)
            return
    else:
        target_date = datetime.today().date()

    for channel_id in channel_ids:
        messages = fetch_messages_for_date(slack_client, channel_id, target_date)
        
        if messages:
            collection_name = f"raw_messages_{channel_id}"
            collection = db[collection_name]
            
            # 日付で既存のドキュメントを検索し、あれば削除
            collection.delete_many({"date": target_date.strftime('%Y-%m-%d')})

            # 新しいメッセージを挿入
            document = {
                "date": target_date.strftime('%Y-%m-%d'),
                "messages": messages
            }
            collection.insert_one(document)
            
            print(f"Raw messages for channel {channel_id} on {target_date.strftime('%Y-%m-%d')} saved to MongoDB.")
        else:
            print(f"No messages found for channel {channel_id} on {target_date.strftime('%Y-%m-%d')}. Nothing was saved to MongoDB.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()