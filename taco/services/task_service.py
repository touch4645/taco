"""
タスク管理サービス
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time

from taco.config.settings import get_settings
from taco.models.task import Task, TaskStatus
from taco.services.backlog_service import BacklogService, BacklogAPIError
from taco.utils.database import execute_query, save_task

logger = logging.getLogger(__name__)

class TaskServiceError(Exception):
    """
    タスクサービス関連のエラー
    """
    pass


class TaskService:
    """
    タスク管理を行うサービス
    """
    def __init__(self):
        """
        設定を読み込み、Backlogサービスを初期化
        """
        self.settings = get_settings()
        self.backlog_service = BacklogService()
        self.cache_ttl = timedelta(minutes=self.settings.cache_ttl_minutes)
        
    def get_all_tasks(self, project_ids: List[str] = None, use_cache: bool = True) -> List[Task]:
        """
        すべてのタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            タスクのリスト
        """
        if project_ids is None:
            project_ids = self.settings.get_backlog_project_ids_list()
            
        all_tasks = []
        
        for project_id in project_ids:
            try:
                # キャッシュを確認
                if use_cache:
                    cached_tasks = self._get_cached_tasks(project_id)
                    if cached_tasks:
                        all_tasks.extend(cached_tasks)
                        continue
                        
                # キャッシュがない場合はAPIから取得
                tasks = self.backlog_service.fetch_all_project_tasks(project_id)
                all_tasks.extend(tasks)
                
            except BacklogAPIError as e:
                logger.error(f"プロジェクト {project_id} のタスク取得中にエラーが発生しました: {str(e)}")
                continue
                
        return all_tasks
    
    def get_overdue_tasks(self, project_ids: List[str] = None, use_cache: bool = True) -> List[Task]:
        """
        期限切れのタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            期限切れのタスクのリスト
        """
        if use_cache:
            # キャッシュから期限切れタスクを取得
            overdue_tasks = self._get_cached_overdue_tasks()
            if overdue_tasks:
                return overdue_tasks
                
        # キャッシュがない場合はBacklogサービスから取得
        return self.backlog_service.get_overdue_tasks(project_ids)
    
    def get_tasks_due_today(self, project_ids: List[str] = None, use_cache: bool = True) -> List[Task]:
        """
        今日期限のタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            今日期限のタスクのリスト
        """
        today = datetime.now().date()
        
        if use_cache:
            # キャッシュから今日期限のタスクを取得
            due_today_tasks = self._get_cached_tasks_due_on(today)
            if due_today_tasks:
                return due_today_tasks
                
        # すべてのタスクを取得して今日期限のものをフィルタリング
        all_tasks = self.get_all_tasks(project_ids, use_cache)
        return [task for task in all_tasks if task.is_due_today]
    
    def get_tasks_due_this_week(self, project_ids: List[str] = None, use_cache: bool = True) -> List[Task]:
        """
        今週期限のタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            今週期限のタスクのリスト
        """
        if use_cache:
            # キャッシュから今週期限のタスクを取得
            due_this_week_tasks = self._get_cached_tasks_due_this_week()
            if due_this_week_tasks:
                return due_this_week_tasks
                
        # キャッシュがない場合はBacklogサービスから取得
        return self.backlog_service.get_upcoming_tasks(days=7, project_ids=project_ids)
    
    def get_tasks_by_assignee(self, assignee_id: str, project_ids: List[str] = None, 
                             use_cache: bool = True) -> List[Task]:
        """
        担当者のタスクを取得
        
        Args:
            assignee_id: 担当者ID
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            担当者のタスクのリスト
        """
        if use_cache:
            # キャッシュから担当者のタスクを取得
            assignee_tasks = self._get_cached_tasks_by_assignee(assignee_id)
            if assignee_tasks:
                return assignee_tasks
                
        # すべてのタスクを取得して担当者でフィルタリング
        all_tasks = self.get_all_tasks(project_ids, use_cache)
        return [task for task in all_tasks if task.assignee_id == assignee_id]
    
    def get_unassigned_tasks(self, project_ids: List[str] = None, use_cache: bool = True) -> List[Task]:
        """
        未割り当てのタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            未割り当てのタスクのリスト
        """
        # すべてのタスクを取得して未割り当てのものをフィルタリング
        all_tasks = self.get_all_tasks(project_ids, use_cache)
        return [task for task in all_tasks if task.assignee_id is None]
    
    def get_task_by_id(self, task_id: str, use_cache: bool = True) -> Optional[Task]:
        """
        IDでタスクを取得
        
        Args:
            task_id: タスクID
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            タスクオブジェクト（見つからない場合はNone）
        """
        if use_cache:
            # キャッシュからタスクを取得
            cached_task = self._get_cached_task_by_id(task_id)
            if cached_task:
                return cached_task
                
        try:
            # BacklogからタスクをAPIで取得
            issue = self.backlog_service.get_issue(task_id)
            task = Task.from_backlog_api(issue)
            
            # キャッシュに保存
            task_dict = {
                "id": task.id,
                "project_id": task.project_id,
                "summary": task.summary,
                "assignee_id": task.assignee_id,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "status": task.status.value,
                "priority": task.priority.value,
                "created_at": task.created.isoformat(),
                "updated_at": task.updated.isoformat(),
                "description": task.description,
                "project_name": task.project_name
            }
            save_task(task_dict)
            
            return task
        except BacklogAPIError as e:
            logger.error(f"タスク {task_id} の取得中にエラーが発生しました: {str(e)}")
            return None
    
    def get_completion_rate(self, project_ids: List[str] = None, use_cache: bool = True) -> float:
        """
        タスクの完了率を計算
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            use_cache: キャッシュを使用するかどうか
            
        Returns:
            完了率（0.0～100.0）
        """
        all_tasks = self.get_all_tasks(project_ids, use_cache)
        
        if not all_tasks:
            return 0.0
            
        completed_tasks = [task for task in all_tasks if task.status in [TaskStatus.RESOLVED, TaskStatus.CLOSED]]
        
        return (len(completed_tasks) / len(all_tasks)) * 100.0
    
    def _get_cached_tasks(self, project_id: str) -> List[Task]:
        """
        キャッシュからプロジェクトのタスクを取得
        
        Args:
            project_id: プロジェクトID
            
        Returns:
            タスクのリスト（キャッシュがない場合は空リスト）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE project_id = ? AND cached_at > ?
        """
        
        result = execute_query(query, (project_id, cache_valid_time_str))
        
        if not result:
            return []
            
        tasks = []
        for row in result:
            try:
                # TaskStatusとPriorityを文字列から列挙型に変換
                status = TaskStatus(row["status"])
                
                # 日付文字列をdatetimeに変換
                created_at = datetime.fromisoformat(row["created_at"])
                updated_at = datetime.fromisoformat(row["updated_at"])
                
                due_date = None
                if row["due_date"]:
                    due_date = datetime.fromisoformat(row["due_date"])
                    
                task = Task(
                    id=row["id"],
                    summary=row["summary"],
                    assignee_id=row["assignee_id"],
                    due_date=due_date,
                    status=status,
                    priority=row["priority"],
                    created=created_at,
                    updated=updated_at,
                    description=row["description"],
                    project_id=row["project_id"],
                    project_name=row["project_name"]
                )
                tasks.append(task)
            except Exception as e:
                logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"キャッシュから {len(tasks)} 件のタスクを取得しました（プロジェクト: {project_id}）")
        return tasks
    
    def _get_cached_overdue_tasks(self) -> List[Task]:
        """
        キャッシュから期限切れのタスクを取得
        
        Returns:
            期限切れのタスクのリスト（キャッシュがない場合は空リスト）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        # 現在の日時
        now = datetime.now().isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE due_date < ? AND status NOT IN ('処理済み', '完了')
        AND cached_at > ?
        """
        
        result = execute_query(query, (now, cache_valid_time_str))
        
        if not result:
            return []
            
        tasks = []
        for row in result:
            try:
                # TaskStatusとPriorityを文字列から列挙型に変換
                status = TaskStatus(row["status"])
                
                # 日付文字列をdatetimeに変換
                created_at = datetime.fromisoformat(row["created_at"])
                updated_at = datetime.fromisoformat(row["updated_at"])
                
                due_date = None
                if row["due_date"]:
                    due_date = datetime.fromisoformat(row["due_date"])
                    
                task = Task(
                    id=row["id"],
                    summary=row["summary"],
                    assignee_id=row["assignee_id"],
                    due_date=due_date,
                    status=status,
                    priority=row["priority"],
                    created=created_at,
                    updated=updated_at,
                    description=row["description"],
                    project_id=row["project_id"],
                    project_name=row["project_name"]
                )
                tasks.append(task)
            except Exception as e:
                logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"キャッシュから {len(tasks)} 件の期限切れタスクを取得しました")
        return tasks
    
    def _get_cached_tasks_due_on(self, target_date: datetime.date) -> List[Task]:
        """
        キャッシュから特定の日付が期限のタスクを取得
        
        Args:
            target_date: 対象日付
            
        Returns:
            対象日付が期限のタスクのリスト（キャッシュがない場合は空リスト）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        # 対象日付の開始と終了
        start_date = datetime.combine(target_date, datetime.min.time()).isoformat()
        end_date = datetime.combine(target_date, datetime.max.time()).isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE due_date >= ? AND due_date <= ?
        AND status NOT IN ('処理済み', '完了')
        AND cached_at > ?
        """
        
        result = execute_query(query, (start_date, end_date, cache_valid_time_str))
        
        if not result:
            return []
            
        tasks = []
        for row in result:
            try:
                # TaskStatusとPriorityを文字列から列挙型に変換
                status = TaskStatus(row["status"])
                
                # 日付文字列をdatetimeに変換
                created_at = datetime.fromisoformat(row["created_at"])
                updated_at = datetime.fromisoformat(row["updated_at"])
                
                due_date = None
                if row["due_date"]:
                    due_date = datetime.fromisoformat(row["due_date"])
                    
                task = Task(
                    id=row["id"],
                    summary=row["summary"],
                    assignee_id=row["assignee_id"],
                    due_date=due_date,
                    status=status,
                    priority=row["priority"],
                    created=created_at,
                    updated=updated_at,
                    description=row["description"],
                    project_id=row["project_id"],
                    project_name=row["project_name"]
                )
                tasks.append(task)
            except Exception as e:
                logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"キャッシュから {len(tasks)} 件の {target_date} 期限タスクを取得しました")
        return tasks
    
    def _get_cached_tasks_due_this_week(self) -> List[Task]:
        """
        キャッシュから今週期限のタスクを取得
        
        Returns:
            今週期限のタスクのリスト（キャッシュがない場合は空リスト）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        # 今日と1週間後の日付
        today = datetime.now().date()
        week_later = today + timedelta(days=7)
        
        start_date = datetime.combine(today, datetime.min.time()).isoformat()
        end_date = datetime.combine(week_later, datetime.max.time()).isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE due_date >= ? AND due_date <= ?
        AND status NOT IN ('処理済み', '完了')
        AND cached_at > ?
        """
        
        result = execute_query(query, (start_date, end_date, cache_valid_time_str))
        
        if not result:
            return []
            
        tasks = []
        for row in result:
            try:
                # TaskStatusとPriorityを文字列から列挙型に変換
                status = TaskStatus(row["status"])
                
                # 日付文字列をdatetimeに変換
                created_at = datetime.fromisoformat(row["created_at"])
                updated_at = datetime.fromisoformat(row["updated_at"])
                
                due_date = None
                if row["due_date"]:
                    due_date = datetime.fromisoformat(row["due_date"])
                    
                task = Task(
                    id=row["id"],
                    summary=row["summary"],
                    assignee_id=row["assignee_id"],
                    due_date=due_date,
                    status=status,
                    priority=row["priority"],
                    created=created_at,
                    updated=updated_at,
                    description=row["description"],
                    project_id=row["project_id"],
                    project_name=row["project_name"]
                )
                tasks.append(task)
            except Exception as e:
                logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"キャッシュから {len(tasks)} 件の今週期限タスクを取得しました")
        return tasks
    
    def _get_cached_tasks_by_assignee(self, assignee_id: str) -> List[Task]:
        """
        キャッシュから担当者のタスクを取得
        
        Args:
            assignee_id: 担当者ID
            
        Returns:
            担当者のタスクのリスト（キャッシュがない場合は空リスト）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE assignee_id = ? AND status NOT IN ('処理済み', '完了')
        AND cached_at > ?
        """
        
        result = execute_query(query, (assignee_id, cache_valid_time_str))
        
        if not result:
            return []
            
        tasks = []
        for row in result:
            try:
                # TaskStatusとPriorityを文字列から列挙型に変換
                status = TaskStatus(row["status"])
                
                # 日付文字列をdatetimeに変換
                created_at = datetime.fromisoformat(row["created_at"])
                updated_at = datetime.fromisoformat(row["updated_at"])
                
                due_date = None
                if row["due_date"]:
                    due_date = datetime.fromisoformat(row["due_date"])
                    
                task = Task(
                    id=row["id"],
                    summary=row["summary"],
                    assignee_id=row["assignee_id"],
                    due_date=due_date,
                    status=status,
                    priority=row["priority"],
                    created=created_at,
                    updated=updated_at,
                    description=row["description"],
                    project_id=row["project_id"],
                    project_name=row["project_name"]
                )
                tasks.append(task)
            except Exception as e:
                logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"キャッシュから {len(tasks)} 件の担当者 {assignee_id} のタスクを取得しました")
        return tasks
    
    def _get_cached_task_by_id(self, task_id: str) -> Optional[Task]:
        """
        キャッシュからIDでタスクを取得
        
        Args:
            task_id: タスクID
            
        Returns:
            タスクオブジェクト（キャッシュがない場合はNone）
        """
        # キャッシュの有効期限を計算
        cache_valid_time = datetime.now() - self.cache_ttl
        cache_valid_time_str = cache_valid_time.isoformat()
        
        query = """
        SELECT * FROM tasks
        WHERE id = ? AND cached_at > ?
        """
        
        result = execute_query(query, (task_id, cache_valid_time_str))
        
        if not result or len(result) == 0:
            return None
            
        row = result[0]
        
        try:
            # TaskStatusとPriorityを文字列から列挙型に変換
            status = TaskStatus(row["status"])
            
            # 日付文字列をdatetimeに変換
            created_at = datetime.fromisoformat(row["created_at"])
            updated_at = datetime.fromisoformat(row["updated_at"])
            
            due_date = None
            if row["due_date"]:
                due_date = datetime.fromisoformat(row["due_date"])
                
            task = Task(
                id=row["id"],
                summary=row["summary"],
                assignee_id=row["assignee_id"],
                due_date=due_date,
                status=status,
                priority=row["priority"],
                created=created_at,
                updated=updated_at,
                description=row["description"],
                project_id=row["project_id"],
                project_name=row["project_name"]
            )
            return task
        except Exception as e:
            logger.error(f"キャッシュからのタスク変換中にエラーが発生しました: {str(e)}")
            return None