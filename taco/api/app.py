"""
TACO (Task & Communication Optimizer) FastAPI Application
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from taco.config.settings import get_settings
from taco.services.health_service import HealthChecker, HealthStatus
from taco.services.scheduler_service import SchedulerService
from taco.services.report_service import ReportService
from taco.services.notification_service import NotificationService

# Configure logging
def setup_logging():
    """
    ロギングシステムを設定
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # ルートロガーを設定
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # コンソール出力
            logging.FileHandler(f"logs/taco_{datetime.now().strftime('%Y%m%d')}.log")  # 日付ベースのファイル出力
        ]
    )
    
    # 外部ライブラリのロガーレベルを調整
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# Global instances
scheduler_service = None
slack_bot = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    アプリケーションのライフサイクル管理
    """
    global scheduler_service, slack_bot
    
    # スタートアップ
    logger.info("TACOアプリケーションを開始しています...")
    
    try:
        # データベースを初期化
        from taco.utils.database import init_database
        init_database()
        
        # スケジューラーを開始
        scheduler_service = SchedulerService()
        scheduler_service.start()
        
        # Slackボットを開始
        from taco.bot.slack_handler import SlackBotHandler
        slack_bot = SlackBotHandler()
        slack_bot.start()
        
        logger.info("TACOアプリケーションが正常に開始されました")
        
    except Exception as e:
        logger.error(f"アプリケーション開始中にエラーが発生しました: {str(e)}")
        raise
    
    yield
    
    # シャットダウン
    logger.info("TACOアプリケーションを停止しています...")
    
    if scheduler_service:
        scheduler_service.stop()
        
    if slack_bot:
        slack_bot.stop()
        
    logger.info("TACOアプリケーションが正常に停止されました")

# Create FastAPI app
app = FastAPI(
    title="TACO API",
    description="Task & Communication Optimizer for Project Management",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# グローバル例外ハンドラー
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    グローバル例外ハンドラー
    """
    from taco.utils.error_handler import ErrorHandler
    
    # エラーハンドラーを作成
    handler = ErrorHandler()
    
    # エラーを処理
    error_response = handler.handle_processing_error(
        exc, 
        {"path": request.url.path, "method": request.method}
    )
    
    # 重大なエラーを通知
    handler.notify_critical_error(error_response)
    
    # エラーレスポンスを返す
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict()
    )

# Health check endpoint
@app.get("/health", response_model=HealthStatus, tags=["System"])
async def health_check():
    """
    Check the health of the system and its dependencies
    """
    try:
        health_checker = HealthChecker()
        return health_checker.check_all()
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )

# Manual trigger endpoints
@app.post("/trigger/daily-report", tags=["Triggers"])
async def trigger_daily_report():
    """
    Manually trigger the generation and posting of a daily report
    """
    try:
        report_service = ReportService()
        notification_service = NotificationService()
        
        # 日次レポートを生成
        report = report_service.generate_daily_report()
        
        # Slackに投稿
        success = notification_service.post_daily_report(report)
        
        return {
            "status": "success" if success else "partial_failure",
            "message": "Daily report generated and posted" if success else "Daily report generated but posting failed",
            "report_date": report.date.isoformat(),
            "overdue_tasks": len(report.overdue_tasks),
            "due_today_tasks": len(report.due_today),
            "completion_rate": report.completion_rate
        }
    except Exception as e:
        logger.error(f"Manual daily report trigger failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Daily report generation failed: {str(e)}"
        )

@app.post("/trigger/weekly-report", tags=["Triggers"])
async def trigger_weekly_report():
    """
    Manually trigger the generation and posting of a weekly report
    """
    try:
        report_service = ReportService()
        notification_service = NotificationService()
        
        # 週次レポートを生成
        report = report_service.generate_weekly_report()
        
        # Slackに投稿
        success = notification_service.post_weekly_report(report)
        
        return {
            "status": "success" if success else "partial_failure",
            "message": "Weekly report generated and posted" if success else "Weekly report generated but posting failed",
            "week_start": report.week_start.isoformat(),
            "week_end": report.week_end.isoformat(),
            "completion_rate": report.trends.completion_rate,
            "key_achievements": len(report.key_achievements),
            "blockers": len(report.blockers)
        }
    except Exception as e:
        logger.error(f"Manual weekly report trigger failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Weekly report generation failed: {str(e)}"
        )

@app.post("/trigger/sync-prompt", tags=["Triggers"])
async def trigger_sync_prompt():
    """
    Manually trigger the daily sync prompt
    """
    try:
        notification_service = NotificationService()
        
        # デイリー同期プロンプトを送信
        thread_ts = notification_service.send_sync_prompt()
        
        return {
            "status": "success",
            "message": "Daily sync prompt sent",
            "thread_ts": thread_ts
        }
    except Exception as e:
        logger.error(f"Manual sync prompt trigger failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync prompt sending failed: {str(e)}"
        )

@app.get("/jobs/status", tags=["Jobs"])
async def get_job_status():
    """
    Get the status of scheduled jobs
    """
    global scheduler_service
    
    if not scheduler_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler service is not available"
        )
    
    try:
        job_status = scheduler_service.get_job_status()
        return {
            "status": "success",
            "jobs": job_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Job status retrieval failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job status retrieval failed: {str(e)}"
        )

@app.post("/jobs/{job_id}/trigger", tags=["Jobs"])
async def trigger_job(job_id: str):
    """
    Manually trigger a specific scheduled job
    """
    global scheduler_service
    
    if not scheduler_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler service is not available"
        )
    
    try:
        success = scheduler_service.trigger_job_manually(job_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Job {job_id} triggered successfully",
                "job_id": job_id
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual job trigger failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job trigger failed: {str(e)}"
        )

# Configuration status endpoint
@app.get("/config/status", tags=["System"])
async def config_status(settings=Depends(get_settings)):
    """
    Check the status of the configuration
    """
    # Mask sensitive values
    safe_config = {
        "backlog": {
            "space_key": settings.backlog_space_key,
            "project_ids": settings.backlog_project_ids,
            "api_key_configured": bool(settings.backlog_api_key),
        },
        "slack": {
            "channel_id": settings.slack_channel_id,
            "admin_user_id": settings.slack_admin_user_id,
            "bot_token_configured": bool(settings.slack_bot_token),
            "app_token_configured": bool(settings.slack_app_token),
        },
        "ai": {
            "provider": settings.ai_provider,
            "model": settings.ai_model,
            "api_key_configured": bool(settings.ai_api_key),
        },
        "system": {
            "timezone": settings.timezone,
            "log_level": settings.log_level,
            "database_url": settings.database_url.replace(
                "sqlite:///", "sqlite:///"
            ),  # Hide path
            "cache_ttl_minutes": settings.cache_ttl_minutes,
        },
    }
    return safe_config

# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """
    Root endpoint with basic system information
    """
    return {
        "name": "TACO - Task & Communication Optimizer",
        "version": "0.1.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
    }