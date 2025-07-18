"""
スケジューラーサービス
"""
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, JobEvent
import pytz

from taco.config.settings import get_settings
from taco.services.report_service import ReportService
from taco.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class SchedulerServiceError(Exception):
    """
    スケジューラーサービス関連のエラー
    """
    pass


class SchedulerService:
    """
    定期的なジョブを管理するサービス
    """
    def __init__(self):
        """
        設定を読み込み、スケジューラーを初期化
        """
        self.settings = get_settings()
        self.timezone = pytz.timezone(self.settings.timezone)
        
        # 依存サービスを初期化
        self.report_service = ReportService()
        self.notification_service = NotificationService()
        
        # スケジューラーを初期化
        self.scheduler = BackgroundScheduler(timezone=self.timezone)
        self.scheduler.add_listener(self._handle_job_error, EVENT_JOB_ERROR)
        
        # 同期ミーティングのスレッドID
        self.sync_thread_ts = None
        
        # ジョブの状態を追跡
        self.job_status = {}
        
    def start(self):
        """
        スケジューラーを開始
        """
        if self.scheduler.running:
            logger.warning("スケジューラーは既に実行中です")
            return
            
        # ジョブを設定
        self._setup_jobs()
        
        # スケジューラーを開始
        self.scheduler.start()
        logger.info("スケジューラーを開始しました")
        
    def stop(self):
        """
        スケジューラーを停止
        """
        if not self.scheduler.running:
            logger.warning("スケジューラーは既に停止しています")
            return
            
        self.scheduler.shutdown()
        logger.info("スケジューラーを停止しました")
        
    def _setup_jobs(self):
        """
        定期的なジョブを設定
        """
        # 日次同期ミーティングのプロンプト（平日9:00 JST）
        self.scheduler.add_job(
            self._daily_sync_prompt_job,
            CronTrigger(hour=9, minute=0, day_of_week='mon-fri', timezone=self.timezone),
            id='daily_sync_prompt',
            replace_existing=True
        )
        
        # 日次同期ミーティングのリマインダー（平日9:15 JST）
        self.scheduler.add_job(
            self._daily_sync_reminder_job,
            CronTrigger(hour=9, minute=15, day_of_week='mon-fri', timezone=self.timezone),
            id='daily_sync_reminder',
            replace_existing=True
        )
        
        # 日次同期ミーティングのサマリー（平日9:30 JST）
        self.scheduler.add_job(
            self._daily_sync_summary_job,
            CronTrigger(hour=9, minute=30, day_of_week='mon-fri', timezone=self.timezone),
            id='daily_sync_summary',
            replace_existing=True
        )
        
        # 日次レポート（毎日10:00 JST）
        self.scheduler.add_job(
            self._daily_report_job,
            CronTrigger(hour=10, minute=0, timezone=self.timezone),
            id='daily_report',
            replace_existing=True
        )
        
        # 週次レポート（月曜日11:00 JST）
        self.scheduler.add_job(
            self._weekly_report_job,
            CronTrigger(hour=11, minute=0, day_of_week='mon', timezone=self.timezone),
            id='weekly_report',
            replace_existing=True
        )
        
        logger.info("定期的なジョブを設定しました")
        
    def _handle_job_error(self, event: JobEvent):
        """
        ジョブエラーを処理
        
        Args:
            event: ジョブイベント
        """
        job_id = event.job_id
        exception = event.exception
        
        logger.error(f"ジョブ '{job_id}' の実行中にエラーが発生しました: {str(exception)}")
        
        # 管理者に通知
        try:
            error_message = f"⚠️ ジョブ '{job_id}' の実行中にエラーが発生しました:\n```{str(exception)}```"
            self.notification_service._post_message(
                text=error_message,
                channel=self.settings.slack_admin_user_id
            )
        except Exception as e:
            logger.error(f"エラー通知の送信中にエラーが発生しました: {str(e)}")
            
        # ジョブの再スケジュール（必要に応じて）
        if job_id in ['daily_report', 'weekly_report']:
            self._reschedule_job(job_id)
            
    def _reschedule_job(self, job_id: str, delay_minutes: int = 30):
        """
        ジョブを再スケジュール
        
        Args:
            job_id: ジョブID
            delay_minutes: 遅延時間（分）
        """
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.warning(f"ジョブ '{job_id}' が見つかりません")
                return
                
            # 現在時刻から指定分後に実行
            run_time = datetime.now(self.timezone) + timedelta(minutes=delay_minutes)
            
            # 一時的なジョブを追加
            retry_job_id = f"{job_id}_retry_{int(time.time())}"
            
            if job_id == 'daily_report':
                self.scheduler.add_job(
                    self._daily_report_job,
                    'date',
                    run_date=run_time,
                    id=retry_job_id
                )
            elif job_id == 'weekly_report':
                self.scheduler.add_job(
                    self._weekly_report_job,
                    'date',
                    run_date=run_time,
                    id=retry_job_id
                )
                
            logger.info(f"ジョブ '{job_id}' を {delay_minutes} 分後に再スケジュールしました（ID: {retry_job_id}）")
            
        except Exception as e:
            logger.error(f"ジョブの再スケジュール中にエラーが発生しました: {str(e)}")
            
    def _daily_sync_prompt_job(self):
        """
        日次同期ミーティングのプロンプトを送信するジョブ
        """
        logger.info("日次同期ミーティングのプロンプトを送信します")
        
        try:
            # プロンプトを送信
            self.sync_thread_ts = self.notification_service.send_sync_prompt()
            logger.info(f"日次同期ミーティングのプロンプトを送信しました（スレッドID: {self.sync_thread_ts}）")
        except Exception as e:
            logger.error(f"日次同期ミーティングのプロンプト送信中にエラーが発生しました: {str(e)}")
            self.sync_thread_ts = None
            
    def _daily_sync_reminder_job(self):
        """
        日次同期ミーティングのリマインダーを送信するジョブ
        """
        logger.info("日次同期ミーティングのリマインダーを送信します")
        
        if not self.sync_thread_ts:
            logger.warning("同期ミーティングのスレッドIDがありません")
            return
            
        try:
            # チャンネルのメンバーを取得
            channel_members = self.notification_service.get_channel_users()
            
            # スレッドの返信を取得
            replies = self.notification_service.get_thread_replies(
                self.settings.slack_channel_id,
                self.sync_thread_ts
            )
            
            # 返信したユーザーのIDを収集
            replied_users = set(reply.get("user") for reply in replies if "user" in reply)
            
            # 返信していないユーザーを特定
            unreplied_users = [user for user in channel_members if user not in replied_users]
            
            # ボットユーザーを除外
            unreplied_users = [user for user in unreplied_users if not self._is_bot_user(user)]
            
            if unreplied_users:
                # リマインダーを送信
                self.notification_service.send_reminder(unreplied_users, self.sync_thread_ts)
                logger.info(f"{len(unreplied_users)} 人のユーザーにリマインダーを送信しました")
            else:
                logger.info("リマインドするユーザーはいません")
                
        except Exception as e:
            logger.error(f"日次同期ミーティングのリマインダー送信中にエラーが発生しました: {str(e)}")
            
    def _daily_sync_summary_job(self):
        """
        日次同期ミーティングのサマリーを送信するジョブ
        """
        logger.info("日次同期ミーティングのサマリーを生成します")
        
        if not self.sync_thread_ts:
            logger.warning("同期ミーティングのスレッドIDがありません")
            return
            
        try:
            # スレッドの返信を取得
            replies = self.notification_service.get_thread_replies(
                self.settings.slack_channel_id,
                self.sync_thread_ts
            )
            
            if not replies:
                logger.info("同期ミーティングの返信がありません")
                return
                
            # サマリーメッセージを作成
            summary_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📋 {datetime.now(self.timezone).strftime('%Y年%m月%d日')} デイリー同期サマリー",
                        "emoji": True
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 返信を処理
            for reply in replies:
                user_id = reply.get("user")
                text = reply.get("text", "")
                
                if not user_id or not text:
                    continue
                    
                # ユーザー情報を取得
                user_info = self.notification_service.get_user_info(user_id)
                user_name = user_info.get("real_name") or user_info.get("name") if user_info else f"<@{user_id}>"
                
                # 構造化された更新情報を抽出
                completed = []
                planned = []
                blockers = []
                
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("昨日:") or line.startswith("完了:"):
                        completed = [item.strip() for item in line.split(":", 1)[1].split(",")]
                    elif line.startswith("今日:") or line.startswith("予定:"):
                        planned = [item.strip() for item in line.split(":", 1)[1].split(",")]
                    elif line.startswith("ブロッカー:") or line.startswith("障害:"):
                        blockers = [item.strip() for item in line.split(":", 1)[1].split(",")]
                
                # ユーザーセクションを追加
                summary_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{user_name}*"
                    }
                })
                
                # 完了タスク
                completed_text = "なし" if not completed or (len(completed) == 1 and (not completed[0] or completed[0].lower() == "なし" or completed[0].lower() == "none")) else "\n• " + "\n• ".join(completed)
                summary_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*昨日の完了:*\n{completed_text}"
                    }
                })
                
                # 予定タスク
                planned_text = "なし" if not planned or (len(planned) == 1 and (not planned[0] or planned[0].lower() == "なし" or planned[0].lower() == "none")) else "\n• " + "\n• ".join(planned)
                summary_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*今日の予定:*\n{planned_text}"
                    }
                })
                
                # ブロッカー
                blockers_text = "なし" if not blockers or (len(blockers) == 1 and (not blockers[0] or blockers[0].lower() == "なし" or blockers[0].lower() == "none")) else "\n• " + "\n• ".join(blockers)
                summary_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*ブロッカー:*\n{blockers_text}"
                    }
                })
                
                summary_blocks.append({
                    "type": "divider"
                })
                
            # サマリーを送信
            self.notification_service._post_message(
                text=f"📋 {datetime.now(self.timezone).strftime('%Y年%m月%d日')} デイリー同期サマリー",
                blocks=summary_blocks
            )
            
            logger.info("日次同期ミーティングのサマリーを送信しました")
            
        except Exception as e:
            logger.error(f"日次同期ミーティングのサマリー生成中にエラーが発生しました: {str(e)}")
            
    def _daily_report_job(self):
        """
        日次レポートを生成して投稿するジョブ
        """
        logger.info("日次レポートを生成します")
        
        try:
            # 日次レポートを生成
            report = self.report_service.generate_daily_report()
            
            # Slackに投稿
            self.notification_service.post_daily_report(report)
            
            logger.info("日次レポートを生成して投稿しました")
            
        except Exception as e:
            logger.error(f"日次レポート生成中にエラーが発生しました: {str(e)}")
            raise
            
    def _weekly_report_job(self):
        """
        週次レポートを生成して投稿するジョブ
        """
        logger.info("週次レポートを生成します")
        
        try:
            # 週次レポートを生成
            report = self.report_service.generate_weekly_report()
            
            # Slackに投稿
            self.notification_service.post_weekly_report(report)
            
            logger.info("週次レポートを生成して投稿しました")
            
        except Exception as e:
            logger.error(f"週次レポート生成中にエラーが発生しました: {str(e)}")
            raise
            
    def _is_bot_user(self, user_id: str) -> bool:
        """
        ユーザーがボットかどうかを判定
        
        Args:
            user_id: ユーザーID
            
        Returns:
            ボットかどうか
        """
        try:
            user_info = self.notification_service.get_user_info(user_id)
            return user_info.get("is_bot", False) or user_info.get("is_app_user", False)
        except Exception:
            return False
            
    def get_job_status(self) -> Dict[str, Any]:
        """
        スケジュールされたジョブの状態を取得
        
        Returns:
            ジョブの状態を含む辞書
        """
        job_status = []
        
        for job in self.scheduler.get_jobs():
            # 次回実行時間を計算
            next_run_time = job.next_run_time.astimezone(self.timezone) if job.next_run_time else None
            next_run_str = next_run_time.strftime('%Y-%m-%d %H:%M:%S') if next_run_time else "未スケジュール"
            
            # ジョブの状態を追加
            job_status.append({
                "id": job.id,
                "name": job.name or job.id,
                "next_run": next_run_str,
                "active": job.next_run_time is not None,
                "trigger": str(job.trigger)
            })
            
        return job_status
        
    def trigger_job_manually(self, job_id: str) -> bool:
        """
        ジョブを手動で実行
        
        Args:
            job_id: ジョブID
            
        Returns:
            実行成功したかどうか
        """
        job = self.scheduler.get_job(job_id)
        
        if not job:
            logger.warning(f"ジョブ '{job_id}' が見つかりません")
            return False
            
        try:
            logger.info(f"ジョブ '{job_id}' を手動で実行します")
            
            if job_id == 'daily_sync_prompt':
                self._daily_sync_prompt_job()
            elif job_id == 'daily_sync_reminder':
                self._daily_sync_reminder_job()
            elif job_id == 'daily_sync_summary':
                self._daily_sync_summary_job()
            elif job_id == 'daily_report':
                self._daily_report_job()
            elif job_id == 'weekly_report':
                self._weekly_report_job()
            else:
                # 未知のジョブIDの場合は関数オブジェクトを直接実行
                job.func()
                
            logger.info(f"ジョブ '{job_id}' の手動実行が完了しました")
            return True
            
        except Exception as e:
            logger.error(f"ジョブ '{job_id}' の手動実行中にエラーが発生しました: {str(e)}")
            return False