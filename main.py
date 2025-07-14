
import os
import json
from datetime import datetime, time, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import sys

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
    メイン処理：Slackからメッセージを取得し、JSON形式でファイルに保存する
    """
    load_dotenv()
    slack_token = os.environ.get("SLACK_API_TOKEN")
    channel_ids_str = os.environ.get("SLACK_CHANNEL_IDS")

    if not slack_token or not channel_ids_str:
        print("Error: SLACK_API_TOKEN and SLACK_CHANNEL_IDS must be set in .env file.", file=sys.stderr)
        return

    channel_ids = [c.strip() for c in channel_ids_str.split(',')]
    client = WebClient(token=slack_token)

    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Error: Invalid date format. Please use YYYY-MM-DD. Got: {target_date_str}", file=sys.stderr)
            return
    else:
        target_date = datetime.today().date()

    for channel_id in channel_ids:
        messages = fetch_messages_for_date(client, channel_id, target_date)
        
        if messages:
            # reports/rawディレクトリにJSONファイルを保存
            output_dir = "reports/raw"
            os.makedirs(output_dir, exist_ok=True)
            
            file_path = os.path.join(output_dir, f"raw_messages_{channel_id}_{target_date.strftime('%Y-%m-%d')}.json")
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=2, ensure_ascii=False)
            
            print(f"Raw messages for channel {channel_id} saved to {file_path}")
        else:
            print(f"No messages found for channel {channel_id} on {target_date.strftime('%Y-%m-%d')}. Raw message file was not created.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
