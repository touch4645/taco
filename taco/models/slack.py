"""
Slack関連のデータモデル
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class SlackMessage:
    """
    Slackメッセージを表すデータクラス
    """
    channel_id: str
    user_id: str
    text: str
    timestamp: datetime
    thread_ts: Optional[str] = None
    user_name: Optional[str] = None
    
    @classmethod
    def from_slack_event(cls, event: Dict[str, Any]) -> "SlackMessage":
        """
        Slackイベントからメッセージオブジェクトを作成
        """
        ts = event.get("ts", "0")
        thread_ts = event.get("thread_ts")
        
        # タイムスタンプをdatetimeに変換
        try:
            timestamp = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            timestamp = datetime.now()
            
        return cls(
            channel_id=event.get("channel", ""),
            user_id=event.get("user", ""),
            text=event.get("text", ""),
            timestamp=timestamp,
            thread_ts=thread_ts,
            user_name=event.get("user_name")
        )


@dataclass
class ProgressUpdate:
    """
    Slackから抽出した進捗情報
    """
    user_id: str
    task_reference: Optional[str]
    content: str
    sentiment: str  # positive, neutral, negative
    extracted_at: datetime
    user_name: Optional[str] = None
    
    @classmethod
    def from_message(cls, message: SlackMessage, task_reference: Optional[str] = None, 
                    sentiment: str = "neutral") -> "ProgressUpdate":
        """
        Slackメッセージから進捗情報を作成
        """
        return cls(
            user_id=message.user_id,
            task_reference=task_reference,
            content=message.text,
            sentiment=sentiment,
            extracted_at=datetime.now(),
            user_name=message.user_name
        )


@dataclass
class SyncUpdate:
    """
    デイリー同期ミーティングでの更新情報
    """
    user_id: str
    completed_yesterday: List[str]
    planned_today: List[str]
    blockers: List[str]
    submitted_at: datetime
    user_name: Optional[str] = None
    
    @classmethod
    def from_structured_message(cls, message: SlackMessage) -> Optional["SyncUpdate"]:
        """
        構造化されたメッセージから同期更新情報を作成
        
        期待されるフォーマット:
        ```
        昨日: タスク1, タスク2
        今日: タスク3, タスク4
        ブロッカー: なし
        ```
        """
        text = message.text.strip()
        completed = []
        planned = []
        blockers = []
        
        # 簡易的なパース処理
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("昨日:") or line.startswith("完了:"):
                completed = [item.strip() for item in line.split(":", 1)[1].split(",")]
            elif line.startswith("今日:") or line.startswith("予定:"):
                planned = [item.strip() for item in line.split(":", 1)[1].split(",")]
            elif line.startswith("ブロッカー:") or line.startswith("障害:"):
                blockers = [item.strip() for item in line.split(":", 1)[1].split(",")]
                
        # 少なくとも1つのセクションが存在する場合のみ作成
        if completed or planned or blockers:
            return cls(
                user_id=message.user_id,
                completed_yesterday=completed,
                planned_today=planned,
                blockers=blockers,
                submitted_at=datetime.now(),
                user_name=message.user_name
            )
        return None