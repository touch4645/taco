"""
Slackイベント処理ハンドラー
"""
import logging
import re
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

from taco.config.settings import get_settings
from taco.models.slack import SlackMessage, SyncUpdate
from taco.services.query_service import QueryService, QueryContext
from taco.services.task_service import TaskService
from taco.utils.database import save_sync_update

logger = logging.getLogger(__name__)

class SlackBotError(Exception):
    """
    Slackボット関連のエラー
    """
    pass


class SlackBotHandler:
    """
    Slackイベントを処理するハンドラー
    """
    def __init__(self):
        """
        設定を読み込み、クライアントを初期化
        """
        self.settings = get_settings()
        self.web_client = WebClient(token=self.settings.slack_bot_token)
        
        # Socket Modeクライアントを初期化
        self.socket_client = SocketModeClient(
            app_token=self.settings.slack_app_token,
            web_client=self.web_client
        )
        
        # 依存サービスを初期化
        self.query_service = QueryService()
        self.task_service = TaskService()
        
        # コマンドパターン
        self.command_pattern = re.compile(r"^!taco\s+(.+)$", re.IGNORECASE)
        
        # 同期更新パターン
        self.sync_pattern = re.compile(
            r"昨日[:：]\s*(.+?)\s*(?:今日[:：]|$)"
            r"(?:今日[:：]\s*(.+?)\s*(?:ブロッカー[:：]|$))?"
            r"(?:ブロッカー[:：]\s*(.+?))?$",
            re.DOTALL
        )
        
        # イベントハンドラーを設定
        self._setup_event_handlers()
        
    def start(self):
        """
        ボットを開始
        """
        logger.info("Slackボットを開始します")
        self.socket_client.connect()
        logger.info("Slackボットが接続しました")
        
    def stop(self):
        """
        ボットを停止
        """
        logger.info("Slackボットを停止します")
        self.socket_client.close()
        logger.info("Slackボットが切断されました")
        
    def _setup_event_handlers(self):
        """
        イベントハンドラーを設定
        """
        # メッセージイベント
        self.socket_client.socket_mode_request_listeners.append(self._handle_socket_mode_request)
        
    def _handle_socket_mode_request(self, client: SocketModeClient, request: SocketModeRequest):
        """
        Socket Modeリクエストを処理
        
        Args:
            client: Socket Modeクライアント
            request: Socket Modeリクエスト
        """
        # 受信確認を送信
        response = SocketModeResponse(envelope_id=request.envelope_id)
        client.send_socket_mode_response(response)
        
        # イベントタイプに応じて処理
        if request.type == "events_api":
            # イベントAPIのペイロードを取得
            event = request.payload.get("event", {})
            event_type = event.get("type")
            
            # イベントタイプに応じて処理
            if event_type == "message":
                self._handle_message_event(event)
                
    def _handle_message_event(self, event: Dict[str, Any]):
        """
        メッセージイベントを処理
        
        Args:
            event: メッセージイベント
        """
        # ボットメッセージは無視
        if event.get("subtype") == "bot_message":
            return
            
        # メッセージテキストを取得
        text = event.get("text", "")
        user_id = event.get("user")
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts")
        ts = event.get("ts")
        
        if not text or not user_id or not channel_id:
            return
            
        try:
            # SlackMessageオブジェクトを作成
            message = SlackMessage(
                channel_id=channel_id,
                user_id=user_id,
                text=text,
                timestamp=datetime.fromtimestamp(float(ts)) if ts else datetime.now(),
                thread_ts=thread_ts
            )
            
            # コマンドかどうかを確認
            command_match = self.command_pattern.match(text)
            if command_match:
                # コマンドを処理
                self._handle_command(message, command_match.group(1))
                return
                
            # 同期スレッドの返信かどうかを確認
            if thread_ts:
                # スレッドの最初のメッセージを取得
                try:
                    thread_parent = self.web_client.conversations_history(
                        channel=channel_id,
                        latest=thread_ts,
                        limit=1,
                        inclusive=True
                    )
                    
                    parent_messages = thread_parent.get("messages", [])
                    if parent_messages and "デイリー同期" in parent_messages[0].get("text", ""):
                        # 同期更新を処理
                        self._handle_sync_update(message)
                        return
                except SlackApiError as e:
                    logger.error(f"スレッド親メッセージの取得中にエラーが発生しました: {str(e)}")
                    
            # メンションされているかどうかを確認
            bot_user_id = self._get_bot_user_id()
            if f"<@{bot_user_id}>" in text:
                # メンションを処理
                self._handle_mention(message)
                
        except Exception as e:
            logger.error(f"メッセージイベント処理中にエラーが発生しました: {str(e)}")
            
    def _handle_command(self, message: SlackMessage, command: str):
        """
        コマンドを処理
        
        Args:
            message: Slackメッセージ
            command: コマンド文字列
        """
        logger.info(f"コマンドを処理します: {command}")
        
        # コマンドを小文字に変換
        command_lower = command.lower().strip()
        
        try:
            if command_lower == "help":
                # ヘルプメッセージを送信
                self._send_help_message(message.channel_id)
            elif command_lower == "status":
                # ステータスを送信
                self._send_status_message(message.channel_id)
            elif command_lower.startswith("report"):
                # レポートコマンドを処理
                self._handle_report_command(message, command_lower)
            else:
                # 未知のコマンド
                self._send_message(
                    channel=message.channel_id,
                    text=f"未知のコマンドです: `{command}`\n`!taco help` でヘルプを表示できます。"
                )
        except Exception as e:
            logger.error(f"コマンド処理中にエラーが発生しました: {str(e)}")
            self._send_message(
                channel=message.channel_id,
                text=f"コマンド処理中にエラーが発生しました: {str(e)}"
            )
            
    def _handle_mention(self, message: SlackMessage):
        """
        メンションを処理
        
        Args:
            message: Slackメッセージ
        """
        logger.info(f"メンションを処理します: {message.text}")
        
        try:
            # ボットのユーザーIDを取得
            bot_user_id = self._get_bot_user_id()
            
            # メンションを除去
            text = message.text.replace(f"<@{bot_user_id}>", "").strip()
            
            # クエリコンテキストを作成
            context = QueryContext(
                user_id=message.user_id,
                channel_id=message.channel_id,
                project_ids=self.settings.get_backlog_project_ids_list()
            )
            
            # 自然言語クエリを処理
            response = self.query_service.process_natural_language_query(text, context)
            
            # 返信を送信
            self._send_message(
                channel=message.channel_id,
                text=response,
                thread_ts=message.thread_ts
            )
            
        except Exception as e:
            logger.error(f"メンション処理中にエラーが発生しました: {str(e)}")
            self._send_message(
                channel=message.channel_id,
                text=f"メンション処理中にエラーが発生しました: {str(e)}",
                thread_ts=message.thread_ts
            )
            
    def _handle_sync_update(self, message: SlackMessage):
        """
        同期更新を処理
        
        Args:
            message: Slackメッセージ
        """
        logger.info(f"同期更新を処理します: {message.text}")
        
        try:
            # 同期更新パターンにマッチするか確認
            match = self.sync_pattern.search(message.text)
            
            if match:
                # グループを取得
                yesterday = match.group(1).strip() if match.group(1) else ""
                today = match.group(2).strip() if match.group(2) else ""
                blockers = match.group(3).strip() if match.group(3) else ""
                
                # リストに変換
                yesterday_list = [item.strip() for item in yesterday.split(",")]
                today_list = [item.strip() for item in today.split(",")]
                blockers_list = [item.strip() for item in blockers.split(",")]
                
                # ユーザー情報を取得
                user_info = self._get_user_info(message.user_id)
                user_name = user_info.get("real_name") or user_info.get("name") if user_info else None
                
                # SyncUpdateオブジェクトを作成
                sync_update = SyncUpdate(
                    user_id=message.user_id,
                    completed_yesterday=yesterday_list,
                    planned_today=today_list,
                    blockers=blockers_list,
                    submitted_at=datetime.now(),
                    user_name=user_name
                )
                
                # データベースに保存
                sync_data = {
                    "user_id": sync_update.user_id,
                    "completed_yesterday": sync_update.completed_yesterday,
                    "planned_today": sync_update.planned_today,
                    "blockers": sync_update.blockers,
                    "submitted_at": sync_update.submitted_at.isoformat(),
                    "user_name": sync_update.user_name
                }
                save_sync_update(sync_data)
                
                # 確認メッセージを送信
                self._send_message(
                    channel=message.channel_id,
                    text=f"同期更新を受け付けました。ありがとうございます！",
                    thread_ts=message.thread_ts
                )
            else:
                # フォーマットが正しくない場合はヘルプを送信
                self._send_message(
                    channel=message.channel_id,
                    text="同期更新のフォーマットが正しくありません。以下のフォーマットで送信してください：\n"
                         "```\n昨日: 完了したタスク\n今日: 予定しているタスク\nブロッカー: 障害や課題\n```",
                    thread_ts=message.thread_ts
                )
                
        except Exception as e:
            logger.error(f"同期更新処理中にエラーが発生しました: {str(e)}")
            self._send_message(
                channel=message.channel_id,
                text=f"同期更新処理中にエラーが発生しました: {str(e)}",
                thread_ts=message.thread_ts
            )
            
    def _handle_report_command(self, message: SlackMessage, command: str):
        """
        レポートコマンドを処理
        
        Args:
            message: Slackメッセージ
            command: コマンド文字列
        """
        # コマンドを解析
        parts = command.split()
        
        if len(parts) < 2:
            self._send_message(
                channel=message.channel_id,
                text="レポートコマンドの形式が正しくありません。\n"
                     "`!taco report daily` または `!taco report weekly` を使用してください。"
            )
            return
            
        report_type = parts[1]
        
        if report_type == "daily":
            # 日次レポートを生成
            self._send_message(
                channel=message.channel_id,
                text="日次レポートを生成中です..."
            )
            
            # APIエンドポイントを呼び出し
            from taco.api.app import trigger_daily_report
            result = trigger_daily_report()
            
            self._send_message(
                channel=message.channel_id,
                text=f"日次レポートを生成しました。\n"
                     f"状態: {result.get('status')}\n"
                     f"期限切れタスク: {result.get('overdue_tasks')} 件\n"
                     f"今日期限タスク: {result.get('due_today_tasks')} 件\n"
                     f"完了率: {result.get('completion_rate'):.1f}%"
            )
            
        elif report_type == "weekly":
            # 週次レポートを生成
            self._send_message(
                channel=message.channel_id,
                text="週次レポートを生成中です..."
            )
            
            # APIエンドポイントを呼び出し
            from taco.api.app import trigger_weekly_report
            result = trigger_weekly_report()
            
            self._send_message(
                channel=message.channel_id,
                text=f"週次レポートを生成しました。\n"
                     f"状態: {result.get('status')}\n"
                     f"期間: {result.get('week_start')} - {result.get('week_end')}\n"
                     f"完了率: {result.get('completion_rate'):.1f}%\n"
                     f"主要な成果: {result.get('key_achievements')} 件\n"
                     f"ブロッカー: {result.get('blockers')} 件"
            )
            
        else:
            self._send_message(
                channel=message.channel_id,
                text=f"未知のレポートタイプです: {report_type}\n"
                     "`!taco report daily` または `!taco report weekly` を使用してください。"
            )
            
    def _send_help_message(self, channel: str):
        """
        ヘルプメッセージを送信
        
        Args:
            channel: チャンネルID
        """
        help_text = """
*TACO - Task & Communication Optimizer*

以下のコマンドが利用可能です：

• `!taco help` - このヘルプメッセージを表示
• `!taco status` - システムの状態を表示
• `!taco report daily` - 日次レポートを手動で生成
• `!taco report weekly` - 週次レポートを手動で生成

また、以下の方法でTACOと対話できます：

• `@TACO 今週のタスクは？` - 自然言語でタスク情報を問い合わせ
• デイリー同期スレッドで更新情報を共有（フォーマット：昨日: 完了タスク、今日: 予定タスク、ブロッカー: 障害）
        """
        
        self._send_message(channel=channel, text=help_text)
        
    def _send_status_message(self, channel: str):
        """
        ステータスメッセージを送信
        
        Args:
            channel: チャンネルID
        """
        # システム情報を収集
        from taco.api.app import health_check
        health_status = health_check()
        
        # ステータスメッセージを作成
        status_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 TACO システム状態",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*全体状態:*\n{health_status.status}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*タイムスタンプ:*\n{health_status.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
        
        # サービス状態を追加
        for service_name, service_health in health_status.services.items():
            status_emoji = "🟢" if service_health.status == "healthy" else "🟡" if service_health.status == "degraded" else "🔴"
            
            status_blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*{service_name}:*\n{status_emoji} {service_health.status}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*メッセージ:*\n{service_health.message}"
                    }
                ]
            })
            
        # ジョブ状態を追加
        from taco.api.app import get_job_status
        job_status = get_job_status()
        
        status_blocks.append({
            "type": "divider"
        })
        
        status_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*スケジュールされたジョブ:*"
            }
        })
        
        for job in job_status.get("jobs", []):
            status_blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*{job.get('name', job.get('id'))}:*\n{job.get('status', 'unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*次回実行:*\n{job.get('next_run', '未スケジュール')}"
                    }
                ]
            })
            
        # メッセージを送信
        self._send_message(
            channel=channel,
            text="TACO システム状態",
            blocks=status_blocks
        )
        
    def _send_message(self, channel: str, text: str, thread_ts: str = None, blocks: List[Dict] = None):
        """
        メッセージを送信
        
        Args:
            channel: チャンネルID
            text: メッセージテキスト
            thread_ts: スレッドタイムスタンプ（オプション）
            blocks: Block Kit形式のブロック（オプション）
        """
        try:
            kwargs = {
                "channel": channel,
                "text": text
            }
            
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
                
            if blocks:
                kwargs["blocks"] = blocks
                
            self.web_client.chat_postMessage(**kwargs)
            
        except SlackApiError as e:
            logger.error(f"メッセージ送信中にエラーが発生しました: {str(e)}")
            
    def _get_bot_user_id(self) -> str:
        """
        ボットのユーザーIDを取得
        
        Returns:
            ボットのユーザーID
        """
        try:
            response = self.web_client.auth_test()
            return response["user_id"]
        except SlackApiError as e:
            logger.error(f"ボットユーザーID取得中にエラーが発生しました: {str(e)}")
            return ""
            
    def _get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        ユーザー情報を取得
        
        Args:
            user_id: ユーザーID
            
        Returns:
            ユーザー情報
        """
        try:
            response = self.web_client.users_info(user=user_id)
            return response["user"]
        except SlackApiError as e:
            logger.error(f"ユーザー情報取得中にエラーが発生しました: {str(e)}")
            return {}