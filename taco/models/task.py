"""
Backlogタスク関連のデータモデル
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List


class TaskStatus(str, Enum):
    """
    タスクのステータス
    """
    OPEN = "未対応"
    IN_PROGRESS = "処理中"
    RESOLVED = "処理済み"
    CLOSED = "完了"
    PENDING = "保留"


class Priority(str, Enum):
    """
    タスクの優先度
    """
    HIGH = "高"
    NORMAL = "中"
    LOW = "低"


@dataclass
class Task:
    """
    Backlogタスクを表すデータクラス
    """
    id: str
    summary: str
    assignee_id: Optional[str]
    due_date: Optional[datetime]
    status: TaskStatus
    priority: Priority
    created: datetime
    updated: datetime
    description: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    
    @property
    def is_overdue(self) -> bool:
        """
        タスクが期限切れかどうかを判定
        """
        if not self.due_date:
            return False
        return self.due_date < datetime.now() and self.status not in [TaskStatus.RESOLVED, TaskStatus.CLOSED]
    
    @property
    def is_due_today(self) -> bool:
        """
        タスクが今日期限かどうかを判定
        """
        if not self.due_date:
            return False
        today = datetime.now().date()
        return self.due_date.date() == today and self.status not in [TaskStatus.RESOLVED, TaskStatus.CLOSED]
    
    @property
    def is_due_this_week(self) -> bool:
        """
        タスクが今週期限かどうかを判定
        """
        if not self.due_date:
            return False
        today = datetime.now().date()
        # 今日から7日以内が「今週」と定義
        delta = (self.due_date.date() - today).days
        return 0 <= delta <= 7 and self.status not in [TaskStatus.RESOLVED, TaskStatus.CLOSED]
    
    @classmethod
    def from_backlog_api(cls, data: dict) -> "Task":
        """
        Backlog APIのレスポンスからTaskオブジェクトを作成
        """
        assignee = data.get("assignee")
        assignee_id = assignee["id"] if assignee else None
        
        status_value = data.get("status", {}).get("name", "未対応")
        try:
            status = TaskStatus(status_value)
        except ValueError:
            status = TaskStatus.OPEN
            
        priority_value = data.get("priority", {}).get("name", "中")
        try:
            priority = Priority(priority_value)
        except ValueError:
            priority = Priority.NORMAL
            
        due_date_str = data.get("dueDate")
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
                
        return cls(
            id=str(data["issueKey"]),
            summary=data["summary"],
            assignee_id=assignee_id,
            due_date=due_date,
            status=status,
            priority=priority,
            created=datetime.fromisoformat(data["created"].replace("Z", "+00:00")),
            updated=datetime.fromisoformat(data["updated"].replace("Z", "+00:00")),
            description=data.get("description"),
            project_id=str(data["projectId"]),
            project_name=data.get("project", {}).get("name")
        )