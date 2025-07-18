"""
Backlog APIとの統合サービス
"""
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time

from taco.config.settings import get_settings
from taco.models.task import Task
from taco.utils.database import save_task, save_user_mapping

logger = logging.getLogger(__name__)

class BacklogAPIError(Exception):
    """
    Backlog API関連のエラー
    """
    pass


class BacklogService:
    """
    Backlog APIとの統合を管理するサービス
    """
    def __init__(self):
        """
        設定を読み込み、APIクライアントを初期化
        """
        self.settings = get_settings()
        self.space_key = self.settings.backlog_space_key
        self.api_key = self.settings.backlog_api_key
        self.base_url = f"https://{self.space_key}.backlog.com/api/v2"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        
    def _make_request(self, method: str, endpoint: str, params: Dict = None, 
                     data: Dict = None, retry_count: int = 3) -> Dict:
        """
        Backlog APIにリクエストを送信
        
        Args:
            method: HTTPメソッド（GET, POST, PUT, DELETE）
            endpoint: APIエンドポイント（/で始まる）
            params: クエリパラメータ
            data: リクエストボディ
            retry_count: リトライ回数
            
        Returns:
            APIレスポンス（JSON）
            
        Raises:
            BacklogAPIError: API呼び出しに失敗した場合
        """
        if params is None:
            params = {}
            
        # API Keyをクエリパラメータとして追加
        params["apiKey"] = self.api_key
        
        url = f"{self.base_url}{endpoint}"
        
        # デバッグ情報を出力
        logger.debug(f"Backlog API リクエスト: {method} {url}")
        logger.debug(f"パラメータ: {params}")
        
        for attempt in range(retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data
                )
                
                # レスポンスをチェック
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # レート制限に達した場合は待機してリトライ
                    wait_time = min(2 ** attempt, 60)  # 指数バックオフ（最大60秒）
                    logger.warning(f"レート制限に達しました。{wait_time}秒待機してリトライします。")
                    time.sleep(wait_time)
                    continue
                else:
                    # その他のエラー
                    error_msg = f"Backlog API エラー: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise BacklogAPIError(error_msg)
                    
            except requests.RequestException as e:
                # ネットワークエラーなど
                if attempt < retry_count - 1:
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(f"リクエストエラー: {str(e)}。{wait_time}秒待機してリトライします。")
                    time.sleep(wait_time)
                    continue
                else:
                    error_msg = f"Backlog APIリクエスト失敗: {str(e)}"
                    logger.error(error_msg)
                    raise BacklogAPIError(error_msg)
                    
        # すべてのリトライが失敗した場合
        raise BacklogAPIError("最大リトライ回数に達しました")
    
    def get_space_info(self) -> Dict:
        """
        スペース情報を取得
        """
        return self._make_request("GET", "/space")
    
    def get_projects(self) -> List[Dict]:
        """
        アクセス可能なプロジェクト一覧を取得
        """
        return self._make_request("GET", "/projects")
    
    def get_project(self, project_id_or_key: str) -> Dict:
        """
        プロジェクト情報を取得
        """
        return self._make_request("GET", f"/projects/{project_id_or_key}")
    
    def get_project_users(self, project_id_or_key: str) -> List[Dict]:
        """
        プロジェクトのユーザー一覧を取得
        """
        return self._make_request("GET", f"/projects/{project_id_or_key}/users")
    
    def get_issues(self, project_id_or_key: str, params: Dict = None) -> List[Dict]:
        """
        課題一覧を取得
        
        Args:
            project_id_or_key: プロジェクトIDまたはキー
            params: 検索条件（オプション）
                - statusId: ステータスID
                - assigneeId: 担当者ID
                - dueDateSince: 期限日（この日付以降）
                - dueDateUntil: 期限日（この日付以前）
                - sort: ソートキー
                - count: 取得上限（デフォルト: 100）
                - offset: オフセット（ページング用）
        """
        if params is None:
            params = {}
            
        # デフォルトで100件取得
        if "count" not in params:
            params["count"] = 100
            
        return self._make_request("GET", f"/projects/{project_id_or_key}/issues", params=params)
    
    def get_issue(self, issue_id_or_key: str) -> Dict:
        """
        課題の詳細を取得
        """
        return self._make_request("GET", f"/issues/{issue_id_or_key}")
    
    def get_user(self, user_id: str) -> Dict:
        """
        ユーザー情報を取得
        """
        return self._make_request("GET", f"/users/{user_id}")
    
    def fetch_all_project_tasks(self, project_id: str) -> List[Task]:
        """
        プロジェクトの全タスクを取得してTaskオブジェクトに変換
        
        Args:
            project_id: プロジェクトID
            
        Returns:
            Taskオブジェクトのリスト
        """
        logger.info(f"プロジェクト {project_id} のタスクを取得中...")
        
        # 課題一覧を取得
        raw_issues = self.get_issues(project_id)
        
        # Taskオブジェクトに変換
        tasks = []
        for issue in raw_issues:
            try:
                task = Task.from_backlog_api(issue)
                tasks.append(task)
                
                # データベースにタスクを保存
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
                
            except Exception as e:
                logger.error(f"タスクの変換中にエラーが発生しました: {str(e)}")
                logger.error(f"問題のあるデータ: {issue}")
                continue
                
        logger.info(f"{len(tasks)} 件のタスクを取得しました")
        return tasks
    
    def get_overdue_tasks(self, project_ids: List[str] = None) -> List[Task]:
        """
        期限切れのタスクを取得
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            
        Returns:
            期限切れのTaskオブジェクトのリスト
        """
        if project_ids is None:
            project_ids = self.settings.get_backlog_project_ids_list()
            
        overdue_tasks = []
        today = datetime.now().date()
        
        for project_id in project_ids:
            try:
                # 期限が過去で、未完了のタスクを取得
                params = {
                    "dueDateUntil": today.isoformat(),
                    "statusId[]": [1, 2, 3]  # 未対応, 処理中, 処理済み
                }
                
                raw_issues = self.get_issues(project_id, params)
                
                for issue in raw_issues:
                    try:
                        task = Task.from_backlog_api(issue)
                        if task.is_overdue:
                            overdue_tasks.append(task)
                            
                            # データベースにタスクを保存
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
                            
                    except Exception as e:
                        logger.error(f"タスクの変換中にエラーが発生しました: {str(e)}")
                        continue
                        
            except BacklogAPIError as e:
                logger.error(f"プロジェクト {project_id} のタスク取得中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"{len(overdue_tasks)} 件の期限切れタスクを取得しました")
        return overdue_tasks
    
    def get_upcoming_tasks(self, days: int = 7, project_ids: List[str] = None) -> List[Task]:
        """
        今後の期限が近いタスクを取得
        
        Args:
            days: 何日以内の期限のタスクを取得するか
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            
        Returns:
            期限が近いTaskオブジェクトのリスト
        """
        if project_ids is None:
            project_ids = self.settings.get_backlog_project_ids_list()
            
        upcoming_tasks = []
        today = datetime.now().date()
        future_date = today + timedelta(days=days)
        
        for project_id in project_ids:
            try:
                # 期限が今日から指定日数以内で、未完了のタスクを取得
                params = {
                    "dueDateSince": today.isoformat(),
                    "dueDateUntil": future_date.isoformat(),
                    "statusId[]": [1, 2, 3]  # 未対応, 処理中, 処理済み
                }
                
                raw_issues = self.get_issues(project_id, params)
                
                for issue in raw_issues:
                    try:
                        task = Task.from_backlog_api(issue)
                        upcoming_tasks.append(task)
                        
                        # データベースにタスクを保存
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
                        
                    except Exception as e:
                        logger.error(f"タスクの変換中にエラーが発生しました: {str(e)}")
                        continue
                        
            except BacklogAPIError as e:
                logger.error(f"プロジェクト {project_id} のタスク取得中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"{len(upcoming_tasks)} 件の今後のタスクを取得しました")
        return upcoming_tasks
    
    def map_users_to_slack(self, project_ids: List[str] = None, slack_user_map: Dict[str, str] = None) -> Dict[str, str]:
        """
        BacklogユーザーとSlackユーザーのマッピングを作成・更新
        
        Args:
            project_ids: プロジェクトIDのリスト（指定がない場合は設定から読み込み）
            slack_user_map: Slackユーザー名とIDのマッピング辞書
            
        Returns:
            BacklogユーザーIDとSlackユーザーIDのマッピング辞書
        """
        if project_ids is None:
            project_ids = self.settings.get_backlog_project_ids_list()
            
        if slack_user_map is None:
            slack_user_map = {}
            
        backlog_to_slack = {}
        
        for project_id in project_ids:
            try:
                # プロジェクトのユーザー一覧を取得
                users = self.get_project_users(project_id)
                
                for user in users:
                    backlog_user_id = str(user["id"])
                    user_name = user.get("name", "")
                    
                    # ユーザー名でSlackユーザーを検索
                    slack_user_id = slack_user_map.get(user_name)
                    
                    if slack_user_id:
                        backlog_to_slack[backlog_user_id] = slack_user_id
                        
                        # データベースにマッピングを保存
                        save_user_mapping(backlog_user_id, slack_user_id, user_name)
                        
            except BacklogAPIError as e:
                logger.error(f"プロジェクト {project_id} のユーザー取得中にエラーが発生しました: {str(e)}")
                continue
                
        logger.info(f"{len(backlog_to_slack)} 件のユーザーマッピングを作成しました")
        return backlog_to_slack