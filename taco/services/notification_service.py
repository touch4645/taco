"""
Slack通知サービス
"""
import logging
import time
from typing import Dict, List, Optional, Union, Any
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from taco.config.settings import get_settings
from taco.models.task import Task
from taco.models.report import DailyReport, WeeklyReport
from taco.utils.database import get_slack_user_id

logger = logging.getLogger(__name__)

class SlackNotificationError(Exception):
    """
    Slack通知関連のエラー
    """
    pass


class NotificationService:
    """
    Slack通知を管理するサービス
    """
    def __init__(self):
        """
        設定を読み込み、Slackクライアントを初期化
        """
        self.settings = get_settings()
        self.client = WebClient(token=self.settings.slack_bot_token)
        self.default_channel = self.settings.slack_channel_id
        self.admin_user = self.settings.slack_admin_user_id
        
    def _post_message(self, text: str, channel: str = None, blocks: List[Dict] = None, 
                     thread_ts: str = None, retry_count: int = 3) -> Dict:
        """
        Slackにメッセージを投稿
        
        Args:
            text: メッセージテキスト
            channel: 投稿先チャンネル（指定がない場合はデフォルトチャンネル）
            blocks: Block Kit形式のメッセージ（オプション）
            thread_ts: スレッドのタイムスタンプ（返信の場合）
            retry_count: リトライ回数
            
        Returns:
            Slack APIレスポンス
            
        Raises:
            SlackNotificationError: 投稿に失敗した場合
        """
        if channel is None:
            channel = self.default_channel
            
        for attempt in range(retry_count):
            try:
                kwargs = {
                    "channel": channel,
                    "text": text
                }
                
                if blocks:
                    kwargs["blocks"] = blocks
                    
                if thread_ts:
                    kwargs["thread_ts"] = thread_ts
                    
                response = self.client.chat_postMessage(**kwargs)
                return response
                
            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    # レート制限に達した場合は待機してリトライ
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning(f"レート制限に達しました。{retry_after}秒待機してリトライします。")
                    time.sleep(retry_after)
                    continue
                elif attempt < retry_count - 1:
                    # その他のエラーでもリトライ
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(f"Slack API エラー: {str(e)}。{wait_time}秒待機してリトライします。")
                    time.sleep(wait_time)
                    continue
                else:
                    error_msg = f"Slackメッセージ投稿失敗: {str(e)}"
                    logger.error(error_msg)
                    raise SlackNotificationError(error_msg)
                    
        # すべてのリトライが失敗した場合
        raise SlackNotificationError("最大リトライ回数に達しました")
    
    def post_daily_report(self, report: DailyReport) -> bool:
        """
        日次レポートをSlackに投稿
        
        Args:
            report: 日次レポートオブジェクト
            
        Returns:
            投稿成功したかどうか
        """
        try:
            # レポートのフォーマット
            date_str = report.date.strftime("%Y年%m月%d日")
            
            # ヘッダーブロック
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 日次進捗レポート: {date_str}",
                        "emoji": True
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 期限切れタスクセクション
            if report.overdue_tasks:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚠️ 期限切れタスク ({len(report.overdue_tasks)}件)*"
                    }
                })
                
                for task in report.overdue_tasks:
                    assignee_mention = ""
                    if task.assignee_id:
                        slack_user_id = get_slack_user_id(task.assignee_id)
                        if slack_user_id:
                            assignee_mention = f"<@{slack_user_id}>"
                            
                    due_date_str = task.due_date.strftime("%Y/%m/%d") if task.due_date else "期限なし"
                    
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• <https://{self.settings.backlog_space_key}.backlog.com/view/{task.id}|{task.id}> {task.summary}\n"
                                   f"  期限: {due_date_str} | 担当: {assignee_mention or '未割り当て'} | 優先度: {task.priority.value}"
                        }
                    })
                    
                blocks.append({
                    "type": "divider"
                })
            
            # 今日期限のタスクセクション
            if report.due_today:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📅 今日期限のタスク ({len(report.due_today)}件)*"
                    }
                })
                
                for task in report.due_today:
                    assignee_mention = ""
                    if task.assignee_id:
                        slack_user_id = get_slack_user_id(task.assignee_id)
                        if slack_user_id:
                            assignee_mention = f"<@{slack_user_id}>"
                            
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• <https://{self.settings.backlog_space_key}.backlog.com/view/{task.id}|{task.id}> {task.summary}\n"
                                   f"  担当: {assignee_mention or '未割り当て'} | 優先度: {task.priority.value}"
                        }
                    })
                    
                blocks.append({
                    "type": "divider"
                })
            
            # 今週期限のタスクセクション（今日期限を除く）
            this_week_tasks = [t for t in report.due_this_week if t not in report.due_today]
            if this_week_tasks:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📆 今週期限のタスク ({len(this_week_tasks)}件)*"
                    }
                })
                
                for task in this_week_tasks:
                    due_date_str = task.due_date.strftime("%Y/%m/%d") if task.due_date else "期限なし"
                    
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• <https://{self.settings.backlog_space_key}.backlog.com/view/{task.id}|{task.id}> {task.summary}\n"
                                   f"  期限: {due_date_str} | 担当: {task.assignee_id or '未割り当て'}"
                        }
                    })
                    
                blocks.append({
                    "type": "divider"
                })
            
            # 進捗情報セクション
            if report.slack_progress:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*💬 昨日のSlackから抽出した進捗情報 ({len(report.slack_progress)}件)*"
                    }
                })
                
                for progress in report.slack_progress[:5]:  # 最大5件まで表示
                    user_mention = f"<@{progress.user_id}>"
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• {user_mention}: {progress.content[:100]}..." if len(progress.content) > 100 else f"• {user_mention}: {progress.content}"
                        }
                    })
                    
                if len(report.slack_progress) > 5:
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"_他 {len(report.slack_progress) - 5} 件の進捗情報があります_"
                        }
                    })
                    
                blocks.append({
                    "type": "divider"
                })
            
            # フッターブロック
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"完了率: {report.completion_rate:.1f}% | 生成日時: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
                    }
                ]
            })
            
            # メッセージを投稿
            summary_text = f"📊 日次進捗レポート: {date_str}"
            if report.has_issues:
                summary_text += f" (⚠️ 期限切れ: {len(report.overdue_tasks)}件, 今日期限: {len(report.due_today)}件)"
            else:
                summary_text += " (問題なし)"
                
            self._post_message(text=summary_text, blocks=blocks)
            logger.info(f"日次レポートを投稿しました: {date_str}")
            return True
            
        except Exception as e:
            logger.error(f"日次レポート投稿中にエラーが発生しました: {str(e)}")
            # 管理者に通知
            try:
                error_message = f"⚠️ 日次レポート投稿中にエラーが発生しました:\n```{str(e)}```"
                self._post_message(text=error_message, channel=self.admin_user)
            except:
                pass
            return False
    
    def post_weekly_report(self, report: WeeklyReport) -> bool:
        """
        週次レポートをSlackに投稿
        
        Args:
            report: 週次レポートオブジェクト
            
        Returns:
            投稿成功したかどうか
        """
        try:
            # レポートのフォーマット
            start_str = report.week_start.strftime("%Y/%m/%d")
            end_str = report.week_end.strftime("%Y/%m/%d")
            
            # ヘッダーブロック
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📈 週次サマリーレポート: {start_str} - {end_str}",
                        "emoji": True
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 主要な成果セクション
            if report.key_achievements:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🏆 主要な成果*"
                    }
                })
                
                achievements_text = "\n".join([f"• {achievement}" for achievement in report.key_achievements])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": achievements_text
                    }
                })
                
                blocks.append({
                    "type": "divider"
                })
            
            # ブロッカーセクション
            if report.blockers:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🚧 ブロッカー*"
                    }
                })
                
                blockers_text = "\n".join([f"• {blocker}" for blocker in report.blockers])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": blockers_text
                    }
                })
                
                blocks.append({
                    "type": "divider"
                })
            
            # 傾向分析セクション
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*📊 傾向分析*"
                }
            })
            
            trend_text = f"• 完了率: {report.trends.completion_rate:.1f}%\n"
            trend_text += f"• 期限切れタスク: {report.trends.overdue_trend:+.1f}% {'増加' if report.trends.overdue_trend > 0 else '減少'}\n"
            trend_text += f"• 平均完了時間: {report.trends.average_completion_time:.1f} 日\n"
            
            if report.trends.recurring_blockers:
                trend_text += "• 繰り返し発生しているブロッカー:\n"
                for blocker in report.trends.recurring_blockers:
                    trend_text += f"  - {blocker}\n"
                    
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": trend_text
                }
            })
            
            blocks.append({
                "type": "divider"
            })
            
            # 推奨アクションセクション
            if report.recommendations:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*💡 推奨アクション*"
                    }
                })
                
                recommendations_text = "\n".join([f"• {rec}" for rec in report.recommendations])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": recommendations_text
                    }
                })
                
                blocks.append({
                    "type": "divider"
                })
            
            # フッターブロック
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"期間: {start_str} - {end_str} | 生成日時: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
                    }
                ]
            })
            
            # メッセージを投稿
            summary_text = f"📈 週次サマリーレポート: {start_str} - {end_str}"
            self._post_message(text=summary_text, blocks=blocks)
            logger.info(f"週次レポートを投稿しました: {start_str} - {end_str}")
            return True
            
        except Exception as e:
            logger.error(f"週次レポート投稿中にエラーが発生しました: {str(e)}")
            # 管理者に通知
            try:
                error_message = f"⚠️ 週次レポート投稿中にエラーが発生しました:\n```{str(e)}```"
                self._post_message(text=error_message, channel=self.admin_user)
            except:
                pass
            return False
    
    def mention_user_for_task(self, task: Task) -> bool:
        """
        タスクの担当者にメンションを送信
        
        Args:
            task: タスクオブジェクト
            
        Returns:
            メンション送信成功したかどうか
        """
        try:
            if not task.assignee_id:
                logger.warning(f"タスク {task.id} には担当者がいません")
                return False
                
            # Backlog担当者IDからSlackユーザーIDを取得
            slack_user_id = get_slack_user_id(task.assignee_id)
            
            if not slack_user_id:
                logger.warning(f"Backlogユーザー {task.assignee_id} に対応するSlackユーザーが見つかりません")
                return False
                
            # メンションメッセージを作成
            due_date_str = task.due_date.strftime("%Y/%m/%d") if task.due_date else "期限なし"
            
            if task.is_overdue:
                message = f"<@{slack_user_id}> 期限切れタスクがあります: "
            elif task.is_due_today:
                message = f"<@{slack_user_id}> 今日が期限のタスクがあります: "
            else:
                message = f"<@{slack_user_id}> タスクの期限が近づいています: "
                
            message += f"<https://{self.settings.backlog_space_key}.backlog.com/view/{task.id}|{task.id}> {task.summary} (期限: {due_date_str})"
            
            # メッセージを投稿
            self._post_message(text=message)
            logger.info(f"ユーザー {slack_user_id} にタスク {task.id} のメンションを送信しました")
            return True
            
        except Exception as e:
            logger.error(f"タスクメンション送信中にエラーが発生しました: {str(e)}")
            return False
    
    def send_sync_prompt(self) -> str:
        """
        デイリー同期ミーティングのプロンプトを送信
        
        Returns:
            メッセージのタイムスタンプ（スレッドID）
        """
        try:
            # 現在の日付
            today = datetime.now().strftime("%Y年%m月%d日")
            
            # プロンプトメッセージを作成
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🌞 おはようございます！{today}のデイリー同期",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "今日のアップデートを共有してください。以下のフォーマットで回答をお願いします："
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "```\n昨日: 完了したタスク\n今日: 予定しているタスク\nブロッカー: 障害や課題\n```"
                    }
                }
            ]
            
            # メッセージを投稿
            response = self._post_message(
                text=f"🌞 {today}のデイリー同期",
                blocks=blocks
            )
            
            logger.info(f"デイリー同期プロンプトを送信しました: {today}")
            return response["ts"]
            
        except Exception as e:
            logger.error(f"デイリー同期プロンプト送信中にエラーが発生しました: {str(e)}")
            # 管理者に通知
            try:
                error_message = f"⚠️ デイリー同期プロンプト送信中にエラーが発生しました:\n```{str(e)}```"
                self._post_message(text=error_message, channel=self.admin_user)
            except:
                pass
            return ""
    
    def send_reminder(self, user_ids: List[str], thread_ts: str) -> bool:
        """
        デイリー同期の未回答者にリマインダーを送信
        
        Args:
            user_ids: リマインドするSlackユーザーIDのリスト
            thread_ts: 元のスレッドのタイムスタンプ
            
        Returns:
            リマインダー送信成功したかどうか
        """
        try:
            if not user_ids:
                logger.info("リマインドするユーザーがいません")
                return True
                
            # メンションリストを作成
            mentions = ", ".join([f"<@{user_id}>" for user_id in user_ids])
            
            # リマインダーメッセージを作成
            message = f"{mentions} デイリー同期の更新をお願いします！"
            
            # メッセージを投稿（スレッド内）
            self._post_message(text=message, thread_ts=thread_ts)
            logger.info(f"{len(user_ids)}人のユーザーにリマインダーを送信しました")
            return True
            
        except Exception as e:
            logger.error(f"リマインダー送信中にエラーが発生しました: {str(e)}")
            return False
    
    def get_channel_users(self, channel_id: str = None) -> List[str]:
        """
        チャンネルのメンバーリストを取得
        
        Args:
            channel_id: チャンネルID（指定がない場合はデフォルトチャンネル）
            
        Returns:
            ユーザーIDのリスト
        """
        if channel_id is None:
            channel_id = self.default_channel
            
        try:
            # チャンネル情報を取得
            response = self.client.conversations_members(channel=channel_id)
            return response["members"]
        except SlackApiError as e:
            logger.error(f"チャンネルメンバー取得中にエラーが発生しました: {str(e)}")
            return []
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Slackユーザー情報を取得
        
        Args:
            user_id: SlackユーザーID
            
        Returns:
            ユーザー情報の辞書
        """
        try:
            response = self.client.users_info(user=user_id)
            return response["user"]
        except SlackApiError as e:
            logger.error(f"ユーザー情報取得中にエラーが発生しました: {str(e)}")
            return {}
    
    def get_channel_history(self, channel_id: str = None, oldest: float = None, 
                           latest: float = None, limit: int = 100) -> List[Dict]:
        """
        チャンネルの履歴を取得
        
        Args:
            channel_id: チャンネルID（指定がない場合はデフォルトチャンネル）
            oldest: 取得開始タイムスタンプ
            latest: 取得終了タイムスタンプ
            limit: 取得上限
            
        Returns:
            メッセージのリスト
        """
        if channel_id is None:
            channel_id = self.default_channel
            
        try:
            params = {"channel": channel_id, "limit": limit}
            
            if oldest:
                params["oldest"] = str(oldest)
                
            if latest:
                params["latest"] = str(latest)
                
            response = self.client.conversations_history(**params)
            return response["messages"]
        except SlackApiError as e:
            logger.error(f"チャンネル履歴取得中にエラーが発生しました: {str(e)}")
            return []
    
    def get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        """
        スレッドの返信を取得
        
        Args:
            channel_id: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            
        Returns:
            返信メッセージのリスト
        """
        try:
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            # 最初のメッセージ（親）を除外
            return response["messages"][1:] if len(response["messages"]) > 1 else []
        except SlackApiError as e:
            logger.error(f"スレッド返信取得中にエラーが発生しました: {str(e)}")
            return []