"""
レポート生成サービス
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import json
import re

from taco.config.settings import get_settings
from taco.models.task import Task
from taco.models.slack import SlackMessage, ProgressUpdate, SyncUpdate
from taco.models.report import DailyReport, WeeklyReport, TrendAnalysis
from taco.services.task_service import TaskService
from taco.services.notification_service import NotificationService
from taco.utils.database import execute_query, save_daily_report, save_weekly_report, save_slack_progress

logger = logging.getLogger(__name__)

class ReportServiceError(Exception):
    """
    レポートサービス関連のエラー
    """
    pass


class ReportService:
    """
    レポート生成を管理するサービス
    """
    def __init__(self):
        """
        設定を読み込み、依存サービスを初期化
        """
        self.settings = get_settings()
        self.task_service = TaskService()
        self.notification_service = NotificationService()
        
        # 進捗キーワード（正規表現）
        self.progress_keywords = [
            r"完了しました",
            r"進捗[：:]",
            r"進めています",
            r"作業中",
            r"取り組んでいます",
            r"ブロック(されて|している)",
            r"遅延",
            r"問題[がは]",
            r"課題[がは]"
        ]
        
        # タスク参照パターン（例: PROJ-123）
        self.task_reference_pattern = r"([A-Z0-9]+-[0-9]+)"
        
    def generate_daily_report(self, target_date: date = None) -> DailyReport:
        """
        日次レポートを生成
        
        Args:
            target_date: 対象日付（指定がない場合は今日）
            
        Returns:
            日次レポートオブジェクト
        """
        if target_date is None:
            target_date = date.today()
            
        logger.info(f"{target_date} の日次レポートを生成します")
        
        try:
            # タスク情報を取得
            overdue_tasks = self.task_service.get_overdue_tasks()
            due_today_tasks = self.task_service.get_tasks_due_today()
            due_this_week_tasks = self.task_service.get_tasks_due_this_week()
            
            # 完了率を計算
            completion_rate = self.task_service.get_completion_rate()
            
            # 前日のSlackメッセージから進捗情報を抽出
            yesterday = target_date - timedelta(days=1)
            slack_progress = self._extract_progress_from_slack(yesterday)
            
            # 同期ミーティングの更新情報を取得
            sync_updates = self._get_sync_updates(target_date)
            
            # 日次レポートを作成
            report = DailyReport(
                date=target_date,
                overdue_tasks=overdue_tasks,
                due_today=due_today_tasks,
                due_this_week=due_this_week_tasks,
                slack_progress=slack_progress,
                sync_updates=sync_updates,
                completion_rate=completion_rate
            )
            
            # データベースに保存
            save_daily_report(target_date.isoformat(), report.to_dict())
            
            logger.info(f"{target_date} の日次レポートを生成しました")
            return report
            
        except Exception as e:
            error_msg = f"{target_date} の日次レポート生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise ReportServiceError(error_msg)
    
    def generate_weekly_report(self, end_date: date = None) -> WeeklyReport:
        """
        週次レポートを生成
        
        Args:
            end_date: 週の終了日（指定がない場合は今日）
            
        Returns:
            週次レポートオブジェクト
        """
        if end_date is None:
            end_date = date.today()
            
        # 週の開始日（終了日から6日前）
        start_date = end_date - timedelta(days=6)
        
        logger.info(f"{start_date} から {end_date} までの週次レポートを生成します")
        
        try:
            # 期間内の日次レポートを取得
            daily_reports = self._get_daily_reports_in_range(start_date, end_date)
            
            if not daily_reports:
                logger.warning(f"期間内の日次レポートがありません: {start_date} - {end_date}")
                # 空の日次レポートを作成
                for day in range(7):
                    current_date = start_date + timedelta(days=day)
                    try:
                        self.generate_daily_report(current_date)
                    except Exception as e:
                        logger.error(f"{current_date} の日次レポート生成中にエラーが発生しました: {str(e)}")
                
                # 再度日次レポートを取得
                daily_reports = self._get_daily_reports_in_range(start_date, end_date)
            
            # 傾向分析を実行
            trends = self._analyze_trends(daily_reports)
            
            # 主要な成果を抽出
            key_achievements = self._extract_key_achievements(daily_reports)
            
            # ブロッカーを抽出
            blockers = self._extract_blockers(daily_reports)
            
            # 推奨アクションを生成
            recommendations = self._generate_recommendations(daily_reports, trends)
            
            # 週次レポートを作成
            report = WeeklyReport(
                week_start=start_date,
                week_end=end_date,
                daily_reports=daily_reports,
                trends=trends,
                key_achievements=key_achievements,
                blockers=blockers,
                recommendations=recommendations
            )
            
            # データベースに保存
            save_weekly_report(
                start_date.isoformat(),
                end_date.isoformat(),
                report.to_dict()
            )
            
            logger.info(f"{start_date} から {end_date} までの週次レポートを生成しました")
            return report
            
        except Exception as e:
            error_msg = f"{start_date} から {end_date} までの週次レポート生成中にエラーが発生しました: {str(e)}"
            logger.error(error_msg)
            raise ReportServiceError(error_msg)
    
    def _extract_progress_from_slack(self, target_date: date) -> List[ProgressUpdate]:
        """
        Slackメッセージから進捗情報を抽出
        
        Args:
            target_date: 対象日付
            
        Returns:
            進捗情報のリスト
        """
        logger.info(f"{target_date} のSlackメッセージから進捗情報を抽出します")
        
        # 対象日の開始と終了のタイムスタンプ
        start_ts = datetime.combine(target_date, datetime.min.time()).timestamp()
        end_ts = datetime.combine(target_date, datetime.max.time()).timestamp()
        
        # Slackからメッセージを取得
        messages = self.notification_service.get_channel_history(
            oldest=start_ts,
            latest=end_ts,
            limit=200
        )
        
        progress_updates = []
        
        for message in messages:
            # ボットのメッセージはスキップ
            if message.get("subtype") == "bot_message":
                continue
                
            text = message.get("text", "")
            user_id = message.get("user")
            ts = message.get("ts")
            
            if not text or not user_id:
                continue
                
            # 進捗キーワードを含むか確認
            is_progress = any(re.search(pattern, text) for pattern in self.progress_keywords)
            
            if is_progress:
                # タスク参照を抽出
                task_refs = re.findall(self.task_reference_pattern, text)
                task_ref = task_refs[0] if task_refs else None
                
                # ユーザー情報を取得
                user_info = self.notification_service.get_user_info(user_id)
                user_name = user_info.get("real_name") or user_info.get("name") if user_info else None
                
                # 感情分析（簡易版）
                sentiment = "neutral"
                if re.search(r"完了|成功|解決", text):
                    sentiment = "positive"
                elif re.search(r"ブロック|遅延|問題|課題|失敗", text):
                    sentiment = "negative"
                
                # SlackMessageオブジェクトを作成
                slack_message = SlackMessage(
                    channel_id=message.get("channel"),
                    user_id=user_id,
                    text=text,
                    timestamp=datetime.fromtimestamp(float(ts)) if ts else datetime.now(),
                    thread_ts=message.get("thread_ts"),
                    user_name=user_name
                )
                
                # ProgressUpdateオブジェクトを作成
                progress_update = ProgressUpdate.from_message(
                    message=slack_message,
                    task_reference=task_ref,
                    sentiment=sentiment
                )
                
                progress_updates.append(progress_update)
                
                # データベースに保存
                progress_data = {
                    "user_id": progress_update.user_id,
                    "task_reference": progress_update.task_reference,
                    "content": progress_update.content,
                    "sentiment": progress_update.sentiment,
                    "extracted_at": progress_update.extracted_at.isoformat(),
                    "message_ts": ts,
                    "channel_id": message.get("channel"),
                    "user_name": progress_update.user_name
                }
                save_slack_progress(progress_data)
                
            # スレッドの返信も確認
            if "thread_ts" in message and message["thread_ts"] == message["ts"]:
                thread_replies = self.notification_service.get_thread_replies(
                    message.get("channel"),
                    message["ts"]
                )
                
                for reply in thread_replies:
                    reply_text = reply.get("text", "")
                    reply_user = reply.get("user")
                    reply_ts = reply.get("ts")
                    
                    if not reply_text or not reply_user or reply.get("subtype") == "bot_message":
                        continue
                        
                    # 進捗キーワードを含むか確認
                    is_reply_progress = any(re.search(pattern, reply_text) for pattern in self.progress_keywords)
                    
                    if is_reply_progress:
                        # タスク参照を抽出
                        reply_task_refs = re.findall(self.task_reference_pattern, reply_text)
                        reply_task_ref = reply_task_refs[0] if reply_task_refs else None
                        
                        # ユーザー情報を取得
                        reply_user_info = self.notification_service.get_user_info(reply_user)
                        reply_user_name = reply_user_info.get("real_name") or reply_user_info.get("name") if reply_user_info else None
                        
                        # 感情分析（簡易版）
                        reply_sentiment = "neutral"
                        if re.search(r"完了|成功|解決", reply_text):
                            reply_sentiment = "positive"
                        elif re.search(r"ブロック|遅延|問題|課題|失敗", reply_text):
                            reply_sentiment = "negative"
                        
                        # SlackMessageオブジェクトを作成
                        reply_slack_message = SlackMessage(
                            channel_id=message.get("channel"),
                            user_id=reply_user,
                            text=reply_text,
                            timestamp=datetime.fromtimestamp(float(reply_ts)) if reply_ts else datetime.now(),
                            thread_ts=message.get("thread_ts"),
                            user_name=reply_user_name
                        )
                        
                        # ProgressUpdateオブジェクトを作成
                        reply_progress_update = ProgressUpdate.from_message(
                            message=reply_slack_message,
                            task_reference=reply_task_ref,
                            sentiment=reply_sentiment
                        )
                        
                        progress_updates.append(reply_progress_update)
                        
                        # データベースに保存
                        reply_progress_data = {
                            "user_id": reply_progress_update.user_id,
                            "task_reference": reply_progress_update.task_reference,
                            "content": reply_progress_update.content,
                            "sentiment": reply_progress_update.sentiment,
                            "extracted_at": reply_progress_update.extracted_at.isoformat(),
                            "message_ts": reply_ts,
                            "channel_id": message.get("channel"),
                            "user_name": reply_progress_update.user_name
                        }
                        save_slack_progress(reply_progress_data)
        
        logger.info(f"{target_date} のSlackメッセージから {len(progress_updates)} 件の進捗情報を抽出しました")
        return progress_updates
    
    def _get_sync_updates(self, target_date: date) -> List[SyncUpdate]:
        """
        同期ミーティングの更新情報を取得
        
        Args:
            target_date: 対象日付
            
        Returns:
            同期更新情報のリスト
        """
        logger.info(f"{target_date} の同期ミーティング更新情報を取得します")
        
        # データベースから同期更新情報を取得
        start_datetime = datetime.combine(target_date, datetime.min.time()).isoformat()
        end_datetime = datetime.combine(target_date, datetime.max.time()).isoformat()
        
        query = """
        SELECT * FROM sync_updates
        WHERE submitted_at >= ? AND submitted_at <= ?
        """
        
        result = execute_query(query, (start_datetime, end_datetime))
        
        if not result:
            logger.info(f"{target_date} の同期ミーティング更新情報はありません")
            return []
            
        sync_updates = []
        for row in result:
            try:
                # JSON文字列をリストに変換
                completed_yesterday = json.loads(row["completed_yesterday"])
                planned_today = json.loads(row["planned_today"])
                blockers = json.loads(row["blockers"])
                
                # 日付文字列をdatetimeに変換
                submitted_at = datetime.fromisoformat(row["submitted_at"])
                
                sync_update = SyncUpdate(
                    user_id=row["user_id"],
                    completed_yesterday=completed_yesterday,
                    planned_today=planned_today,
                    blockers=blockers,
                    submitted_at=submitted_at,
                    user_name=row["user_name"]
                )
                sync_updates.append(sync_update)
            except Exception as e:
                logger.error(f"同期更新情報の変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"{target_date} の同期ミーティングから {len(sync_updates)} 件の更新情報を取得しました")
        return sync_updates
    
    def _get_daily_reports_in_range(self, start_date: date, end_date: date) -> List[DailyReport]:
        """
        指定期間内の日次レポートを取得
        
        Args:
            start_date: 開始日
            end_date: 終了日
            
        Returns:
            日次レポートのリスト
        """
        logger.info(f"{start_date} から {end_date} までの日次レポートを取得します")
        
        query = """
        SELECT * FROM daily_reports
        WHERE report_date >= ? AND report_date <= ?
        ORDER BY report_date ASC
        """
        
        result = execute_query(query, (start_date.isoformat(), end_date.isoformat()))
        
        if not result:
            logger.info(f"{start_date} から {end_date} までの日次レポートはありません")
            return []
            
        # タスクIDからタスクオブジェクトへのマッピングを作成
        task_ids = set()
        for row in result:
            report_data = json.loads(row["report_data"])
            task_ids.update(report_data.get("overdue_tasks", []))
            task_ids.update(report_data.get("due_today", []))
            task_ids.update(report_data.get("due_this_week", []))
            
        tasks_map = {}
        for task_id in task_ids:
            task = self.task_service.get_task_by_id(task_id)
            if task:
                tasks_map[task_id] = task
                
        # 進捗情報を取得
        progress_updates_map = {}
        sync_updates_map = {}
        
        for row in result:
            report_date = date.fromisoformat(row["report_date"])
            
            # 進捗情報を取得
            yesterday = report_date - timedelta(days=1)
            progress_updates = self._extract_progress_from_slack(yesterday)
            progress_updates_map[report_date] = progress_updates
            
            # 同期更新情報を取得
            sync_updates = self._get_sync_updates(report_date)
            sync_updates_map[report_date] = sync_updates
            
        # 日次レポートを作成
        daily_reports = []
        for row in result:
            try:
                report_date = date.fromisoformat(row["report_date"])
                report_data = json.loads(row["report_data"])
                
                daily_report = DailyReport.from_dict(
                    data=report_data,
                    tasks_map=tasks_map,
                    progress_updates=progress_updates_map.get(report_date, []),
                    sync_updates=sync_updates_map.get(report_date, [])
                )
                daily_reports.append(daily_report)
            except Exception as e:
                logger.error(f"日次レポートの変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"{start_date} から {end_date} までの期間で {len(daily_reports)} 件の日次レポートを取得しました")
        return daily_reports
    
    def _analyze_trends(self, daily_reports: List[DailyReport]) -> TrendAnalysis:
        """
        日次レポートから傾向を分析
        
        Args:
            daily_reports: 日次レポートのリスト
            
        Returns:
            傾向分析結果
        """
        if not daily_reports:
            return TrendAnalysis(
                completion_rate=0.0,
                overdue_trend=0.0,
                average_completion_time=0.0,
                recurring_blockers=[]
            )
            
        # 完了率の平均
        completion_rates = [report.completion_rate for report in daily_reports]
        avg_completion_rate = sum(completion_rates) / len(completion_rates)
        
        # 期限切れタスクの傾向
        if len(daily_reports) >= 2:
            first_overdue = len(daily_reports[0].overdue_tasks)
            last_overdue = len(daily_reports[-1].overdue_tasks)
            
            if first_overdue > 0:
                overdue_trend = ((last_overdue - first_overdue) / first_overdue) * 100
            else:
                overdue_trend = 0.0 if last_overdue == 0 else 100.0
        else:
            overdue_trend = 0.0
            
        # 平均完了時間（ダミー値）
        average_completion_time = 3.5
        
        # 繰り返し発生しているブロッカー
        all_blockers = []
        for report in daily_reports:
            for sync_update in report.sync_updates:
                all_blockers.extend(sync_update.blockers)
                
        # ブロッカーの出現回数をカウント
        blocker_counts = {}
        for blocker in all_blockers:
            if blocker and blocker.lower() != "なし" and blocker.lower() != "none":
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
                
        # 2回以上出現したブロッカーを抽出
        recurring_blockers = [blocker for blocker, count in blocker_counts.items() if count >= 2]
        
        return TrendAnalysis(
            completion_rate=avg_completion_rate,
            overdue_trend=overdue_trend,
            average_completion_time=average_completion_time,
            recurring_blockers=recurring_blockers
        )
    
    def _extract_key_achievements(self, daily_reports: List[DailyReport]) -> List[str]:
        """
        日次レポートから主要な成果を抽出
        
        Args:
            daily_reports: 日次レポートのリスト
            
        Returns:
            主要な成果のリスト
        """
        achievements = []
        
        # 完了したタスクを収集
        completed_tasks = set()
        for report in daily_reports:
            for sync_update in report.sync_updates:
                for task in sync_update.completed_yesterday:
                    if task and task.lower() != "なし" and task.lower() != "none":
                        completed_tasks.add(task)
                        
        # ポジティブな進捗情報を収集
        positive_progress = []
        for report in daily_reports:
            for progress in report.slack_progress:
                if progress.sentiment == "positive":
                    positive_progress.append(progress.content)
                    
        # 完了タスクを成果として追加
        for task in list(completed_tasks)[:5]:  # 最大5件
            achievements.append(f"タスク完了: {task}")
            
        # ポジティブな進捗を成果として追加
        for progress in positive_progress[:3]:  # 最大3件
            # 長すぎる場合は省略
            if len(progress) > 100:
                progress = progress[:97] + "..."
            achievements.append(f"進捗: {progress}")
            
        return achievements
    
    def _extract_blockers(self, daily_reports: List[DailyReport]) -> List[str]:
        """
        日次レポートからブロッカーを抽出
        
        Args:
            daily_reports: 日次レポートのリスト
            
        Returns:
            ブロッカーのリスト
        """
        blockers = []
        
        # 同期更新からブロッカーを収集
        sync_blockers = set()
        for report in daily_reports:
            for sync_update in report.sync_updates:
                for blocker in sync_update.blockers:
                    if blocker and blocker.lower() != "なし" and blocker.lower() != "none":
                        sync_blockers.add(blocker)
                        
        # ネガティブな進捗情報を収集
        negative_progress = []
        for report in daily_reports:
            for progress in report.slack_progress:
                if progress.sentiment == "negative":
                    negative_progress.append(progress.content)
                    
        # 同期ブロッカーを追加
        for blocker in list(sync_blockers):
            blockers.append(blocker)
            
        # ネガティブな進捗をブロッカーとして追加
        for progress in negative_progress[:3]:  # 最大3件
            # 長すぎる場合は省略
            if len(progress) > 100:
                progress = progress[:97] + "..."
            blockers.append(f"報告された問題: {progress}")
            
        return blockers
    
    def _generate_recommendations(self, daily_reports: List[DailyReport], 
                                trends: TrendAnalysis) -> List[str]:
        """
        分析結果から推奨アクションを生成
        
        Args:
            daily_reports: 日次レポートのリスト
            trends: 傾向分析結果
            
        Returns:
            推奨アクションのリスト
        """
        recommendations = []
        
        # 期限切れタスクの対応
        overdue_count = sum(len(report.overdue_tasks) for report in daily_reports) // len(daily_reports)
        if overdue_count > 0:
            recommendations.append(f"期限切れタスク（平均{overdue_count}件）の優先対応を検討してください")
            
        # 完了率が低い場合
        if trends.completion_rate < 50:
            recommendations.append("タスク完了率が低いため、スコープの見直しまたはリソース追加を検討してください")
            
        # 期限切れタスクが増加している場合
        if trends.overdue_trend > 10:
            recommendations.append("期限切れタスクが増加傾向にあります。タスクの優先順位付けを見直してください")
            
        # 繰り返し発生しているブロッカーがある場合
        if trends.recurring_blockers:
            recommendations.append("繰り返し発生しているブロッカーに対する対策会議の開催を検討してください")
            
        # 未割り当てタスクがある場合
        unassigned_count = 0
        for report in daily_reports:
            for task in report.overdue_tasks + report.due_today + report.due_this_week:
                if task.assignee_id is None:
                    unassigned_count += 1
                    break
                    
        if unassigned_count > 0:
            recommendations.append("未割り当てのタスクがあります。担当者のアサインを検討してください")
            
        # デフォルトの推奨事項
        if not recommendations:
            recommendations.append("プロジェクトは順調に進行しています。現在の進め方を継続してください")
            
        return recommendations