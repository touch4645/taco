"""
レポート関連のデータモデル
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Dict, Optional, Any

from taco.models.task import Task
from taco.models.slack import ProgressUpdate, SyncUpdate


@dataclass
class TrendAnalysis:
    """
    タスク完了傾向の分析
    """
    completion_rate: float
    overdue_trend: float  # 正: 増加, 負: 減少
    average_completion_time: float  # 日数
    recurring_blockers: List[str]
    

@dataclass
class DailyReport:
    """
    日次レポート
    """
    date: date
    overdue_tasks: List[Task]
    due_today: List[Task]
    due_this_week: List[Task]
    slack_progress: List[ProgressUpdate]
    sync_updates: List[SyncUpdate]
    completion_rate: float
    
    @property
    def has_issues(self) -> bool:
        """
        注意が必要な問題があるかどうか
        """
        return len(self.overdue_tasks) > 0 or len(self.due_today) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """
        レポートを辞書に変換（データベース保存用）
        """
        return {
            "date": self.date.isoformat(),
            "overdue_tasks": [task.id for task in self.overdue_tasks],
            "due_today": [task.id for task in self.due_today],
            "due_this_week": [task.id for task in self.due_this_week],
            "completion_rate": self.completion_rate,
            "slack_progress_count": len(self.slack_progress),
            "sync_updates_count": len(self.sync_updates),
            "created_at": datetime.now().isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], 
                 tasks_map: Dict[str, Task],
                 progress_updates: List[ProgressUpdate],
                 sync_updates: List[SyncUpdate]) -> "DailyReport":
        """
        辞書からレポートを作成（データベースから読み込み用）
        """
        report_date = date.fromisoformat(data["date"])
        
        overdue_tasks = [tasks_map.get(task_id) for task_id in data.get("overdue_tasks", [])]
        due_today = [tasks_map.get(task_id) for task_id in data.get("due_today", [])]
        due_this_week = [tasks_map.get(task_id) for task_id in data.get("due_this_week", [])]
        
        # Noneを除去
        overdue_tasks = [t for t in overdue_tasks if t]
        due_today = [t for t in due_today if t]
        due_this_week = [t for t in due_this_week if t]
        
        return cls(
            date=report_date,
            overdue_tasks=overdue_tasks,
            due_today=due_today,
            due_this_week=due_this_week,
            slack_progress=progress_updates,
            sync_updates=sync_updates,
            completion_rate=data.get("completion_rate", 0.0)
        )


@dataclass
class WeeklyReport:
    """
    週次レポート
    """
    week_start: date
    week_end: date
    daily_reports: List[DailyReport]
    trends: TrendAnalysis
    key_achievements: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        レポートを辞書に変換（データベース保存用）
        """
        return {
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "daily_reports": [d.date.isoformat() for d in self.daily_reports],
            "trends": {
                "completion_rate": self.trends.completion_rate,
                "overdue_trend": self.trends.overdue_trend,
                "average_completion_time": self.trends.average_completion_time,
                "recurring_blockers": self.trends.recurring_blockers
            },
            "key_achievements": self.key_achievements,
            "blockers": self.blockers,
            "recommendations": self.recommendations,
            "created_at": datetime.now().isoformat()
        }