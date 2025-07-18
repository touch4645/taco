"""
データベース接続とスキーマ管理のユーティリティ
"""
import os
import sqlite3
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import json

from taco.config.settings import get_settings

logger = logging.getLogger(__name__)

# SQLiteデータベースのスキーマ定義
SCHEMA_DEFINITIONS = [
    # タスクキャッシュテーブル
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        assignee_id TEXT,
        due_date DATETIME,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        description TEXT,
        project_name TEXT
    )
    """,
    
    # 日次レポートテーブル
    """
    CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date DATE NOT NULL UNIQUE,
        report_data JSON NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # 週次レポートテーブル
    """
    CREATE TABLE IF NOT EXISTS weekly_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_start DATE NOT NULL,
        week_end DATE NOT NULL,
        report_data JSON NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(week_start, week_end)
    )
    """,
    
    # ユーザーマッピングテーブル
    """
    CREATE TABLE IF NOT EXISTS user_mappings (
        backlog_user_id TEXT PRIMARY KEY,
        slack_user_id TEXT NOT NULL,
        display_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # 設定キャッシュテーブル
    """
    CREATE TABLE IF NOT EXISTS config_cache (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Slackメッセージ進捗テーブル
    """
    CREATE TABLE IF NOT EXISTS slack_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        task_reference TEXT,
        content TEXT NOT NULL,
        sentiment TEXT NOT NULL,
        extracted_at DATETIME NOT NULL,
        message_ts TEXT,
        channel_id TEXT,
        user_name TEXT
    )
    """,
    
    # 同期更新テーブル
    """
    CREATE TABLE IF NOT EXISTS sync_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        completed_yesterday JSON NOT NULL,
        planned_today JSON NOT NULL,
        blockers JSON NOT NULL,
        submitted_at DATETIME NOT NULL,
        user_name TEXT
    )
    """
]


def get_db_connection() -> sqlite3.Connection:
    """
    SQLiteデータベースへの接続を取得
    """
    settings = get_settings()
    db_path = settings.database_url.replace("sqlite:///", "")
    
    # データベースディレクトリが存在することを確認
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    # データベース接続を作成し、Row Factory を設定
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    return conn


def init_database() -> None:
    """
    データベースの初期化とスキーマの作成
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # スキーマを作成
        for schema in SCHEMA_DEFINITIONS:
            cursor.execute(schema)
            
        conn.commit()
        logger.info("データベーススキーマが正常に初期化されました")
    except sqlite3.Error as e:
        logger.error(f"データベーススキーマの初期化中にエラーが発生しました: {e}")
        conn.rollback()
    finally:
        conn.close()


def execute_query(query: str, params: Tuple = ()) -> Optional[List[Dict[str, Any]]]:
    """
    SQLクエリを実行し、結果を辞書のリストとして返す
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query, params)
        
        if query.strip().upper().startswith("SELECT"):
            # SELECTクエリの場合は結果を返す
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append({key: row[key] for key in row.keys()})
            return result
        else:
            # INSERT/UPDATE/DELETEの場合はコミットして影響を受けた行数を返す
            conn.commit()
            return [{"affected_rows": cursor.rowcount}]
    except sqlite3.Error as e:
        logger.error(f"クエリ実行中にエラーが発生しました: {e}")
        logger.error(f"クエリ: {query}")
        logger.error(f"パラメータ: {params}")
        conn.rollback()
        return None
    finally:
        conn.close()


def save_task(task_data: Dict[str, Any]) -> bool:
    """
    タスクをデータベースに保存（挿入または更新）
    """
    query = """
    INSERT INTO tasks (
        id, project_id, summary, assignee_id, due_date, status, priority,
        created_at, updated_at, cached_at, description, project_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        project_id = excluded.project_id,
        summary = excluded.summary,
        assignee_id = excluded.assignee_id,
        due_date = excluded.due_date,
        status = excluded.status,
        priority = excluded.priority,
        updated_at = excluded.updated_at,
        cached_at = excluded.cached_at,
        description = excluded.description,
        project_name = excluded.project_name
    """
    
    params = (
        task_data["id"],
        task_data["project_id"],
        task_data["summary"],
        task_data.get("assignee_id"),
        task_data.get("due_date"),
        task_data["status"],
        task_data["priority"],
        task_data["created_at"],
        task_data["updated_at"],
        datetime.now().isoformat(),
        task_data.get("description"),
        task_data.get("project_name")
    )
    
    result = execute_query(query, params)
    return result is not None


def save_daily_report(report_date: str, report_data: Dict[str, Any]) -> bool:
    """
    日次レポートをデータベースに保存
    """
    query = """
    INSERT INTO daily_reports (report_date, report_data)
    VALUES (?, ?)
    ON CONFLICT(report_date) DO UPDATE SET
        report_data = excluded.report_data,
        created_at = CURRENT_TIMESTAMP
    """
    
    params = (report_date, json.dumps(report_data, ensure_ascii=False))
    result = execute_query(query, params)
    return result is not None


def save_weekly_report(week_start: str, week_end: str, report_data: Dict[str, Any]) -> bool:
    """
    週次レポートをデータベースに保存
    """
    query = """
    INSERT INTO weekly_reports (week_start, week_end, report_data)
    VALUES (?, ?, ?)
    ON CONFLICT(week_start, week_end) DO UPDATE SET
        report_data = excluded.report_data,
        created_at = CURRENT_TIMESTAMP
    """
    
    params = (week_start, week_end, json.dumps(report_data, ensure_ascii=False))
    result = execute_query(query, params)
    return result is not None


def save_user_mapping(backlog_user_id: str, slack_user_id: str, display_name: Optional[str] = None) -> bool:
    """
    ユーザーマッピングをデータベースに保存
    """
    query = """
    INSERT INTO user_mappings (backlog_user_id, slack_user_id, display_name)
    VALUES (?, ?, ?)
    ON CONFLICT(backlog_user_id) DO UPDATE SET
        slack_user_id = excluded.slack_user_id,
        display_name = excluded.display_name
    """
    
    params = (backlog_user_id, slack_user_id, display_name)
    result = execute_query(query, params)
    return result is not None


def get_slack_user_id(backlog_user_id: str) -> Optional[str]:
    """
    Backlogユーザーに対応するSlackユーザーIDを取得
    """
    query = "SELECT slack_user_id FROM user_mappings WHERE backlog_user_id = ?"
    result = execute_query(query, (backlog_user_id,))
    
    if result and len(result) > 0:
        return result[0]["slack_user_id"]
    return None


def save_slack_progress(progress_data: Dict[str, Any]) -> bool:
    """
    Slackからの進捗情報をデータベースに保存
    """
    query = """
    INSERT INTO slack_progress (
        user_id, task_reference, content, sentiment, extracted_at,
        message_ts, channel_id, user_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = (
        progress_data["user_id"],
        progress_data.get("task_reference"),
        progress_data["content"],
        progress_data["sentiment"],
        progress_data["extracted_at"],
        progress_data.get("message_ts"),
        progress_data.get("channel_id"),
        progress_data.get("user_name")
    )
    
    result = execute_query(query, params)
    return result is not None


def save_sync_update(sync_data: Dict[str, Any]) -> bool:
    """
    同期更新情報をデータベースに保存
    """
    query = """
    INSERT INTO sync_updates (
        user_id, completed_yesterday, planned_today, blockers,
        submitted_at, user_name
    ) VALUES (?, ?, ?, ?, ?, ?)
    """
    
    params = (
        sync_data["user_id"],
        json.dumps(sync_data["completed_yesterday"], ensure_ascii=False),
        json.dumps(sync_data["planned_today"], ensure_ascii=False),
        json.dumps(sync_data["blockers"], ensure_ascii=False),
        sync_data["submitted_at"],
        sync_data.get("user_name")
    )
    
    result = execute_query(query, params)
    return result is not None