"""
エラーハンドリングユーティリティ
"""
import logging
import traceback
import sys
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import uuid
from functools import wraps

from taco.config.settings import get_settings

logger = logging.getLogger(__name__)

class ErrorResponse:
    """
    エラーレスポンス
    """
    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        self.correlation_id = correlation_id or str(uuid.uuid4())
        
    def to_dict(self) -> Dict[str, Any]:
        """
        辞書に変換
        
        Returns:
            辞書形式のエラーレスポンス
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id
        }
        
    def __str__(self) -> str:
        """
        文字列表現
        
        Returns:
            文字列形式のエラーレスポンス
        """
        return f"[{self.error_code}] {self.message} (ID: {self.correlation_id})"


class ErrorHandler:
    """
    エラーハンドリングユーティリティ
    """
    def __init__(self):
        """
        設定を読み込み
        """
        self.settings = get_settings()
        
    def handle_api_error(self, error: Exception, context: str) -> ErrorResponse:
        """
        API呼び出しエラーを処理
        
        Args:
            error: 発生した例外
            context: エラーのコンテキスト
            
        Returns:
            エラーレスポンス
        """
        error_code = "API_ERROR"
        message = f"外部APIとの通信中にエラーが発生しました: {str(error)}"
        
        # スタックトレースを取得
        stack_trace = traceback.format_exception(type(error), error, error.__traceback__)
        
        # エラー詳細を作成
        details = {
            "context": context,
            "error_type": error.__class__.__name__,
            "stack_trace": stack_trace if self.settings.log_level.upper() == "DEBUG" else None
        }
        
        # エラーをログに記録
        logger.error(f"API Error in {context}: {str(error)}")
        if self.settings.log_level.upper() == "DEBUG":
            logger.debug("".join(stack_trace))
            
        return ErrorResponse(error_code, message, details)
        
    def handle_processing_error(self, error: Exception, data: Any) -> ErrorResponse:
        """
        データ処理エラーを処理
        
        Args:
            error: 発生した例外
            data: 処理中のデータ
            
        Returns:
            エラーレスポンス
        """
        error_code = "PROCESSING_ERROR"
        message = f"データ処理中にエラーが発生しました: {str(error)}"
        
        # スタックトレースを取得
        stack_trace = traceback.format_exception(type(error), error, error.__traceback__)
        
        # エラー詳細を作成
        details = {
            "error_type": error.__class__.__name__,
            "stack_trace": stack_trace if self.settings.log_level.upper() == "DEBUG" else None
        }
        
        # 機密情報を含む可能性があるため、データ自体はログに記録しない
        
        # エラーをログに記録
        logger.error(f"Processing Error: {str(error)}")
        if self.settings.log_level.upper() == "DEBUG":
            logger.debug("".join(stack_trace))
            
        return ErrorResponse(error_code, message, details)
        
    def handle_validation_error(self, error: Exception, field: str) -> ErrorResponse:
        """
        バリデーションエラーを処理
        
        Args:
            error: 発生した例外
            field: バリデーションエラーが発生したフィールド
            
        Returns:
            エラーレスポンス
        """
        error_code = "VALIDATION_ERROR"
        message = f"バリデーションエラー: {str(error)}"
        
        # エラー詳細を作成
        details = {
            "field": field,
            "error_type": error.__class__.__name__
        }
        
        # エラーをログに記録
        logger.warning(f"Validation Error in field '{field}': {str(error)}")
            
        return ErrorResponse(error_code, message, details)
        
    def notify_critical_error(self, error: ErrorResponse) -> None:
        """
        重大なエラーを通知
        
        Args:
            error: エラーレスポンス
        """
        try:
            # Slackに通知
            from taco.services.notification_service import NotificationService
            notification_service = NotificationService()
            
            error_message = f"🚨 *重大なエラーが発生しました*\n"
            error_message += f"*エラーコード:* {error.error_code}\n"
            error_message += f"*メッセージ:* {error.message}\n"
            error_message += f"*相関ID:* {error.correlation_id}\n"
            error_message += f"*タイムスタンプ:* {error.timestamp.isoformat()}"
            
            notification_service._post_message(
                text=error_message,
                channel=self.settings.slack_admin_user_id
            )
            
            logger.info(f"重大なエラーを通知しました: {error}")
            
        except Exception as e:
            logger.error(f"エラー通知中にエラーが発生しました: {str(e)}")


def error_handler(func: Callable) -> Callable:
    """
    エラーハンドリングデコレータ
    
    Args:
        func: デコレートする関数
        
    Returns:
        デコレートされた関数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # エラーハンドラーを作成
            handler = ErrorHandler()
            
            # エラーを処理
            error_response = handler.handle_processing_error(e, {"args": args, "kwargs": kwargs})
            
            # 重大なエラーを通知
            handler.notify_critical_error(error_response)
            
            # 例外を再発生
            raise
            
    return wrapper