"""
TACO (Task & Communication Optimizer) Main Entry Point
"""
import uvicorn
import logging
import os
from datetime import datetime
from taco.api.app import app, setup_logging
from taco.config.settings import get_settings

# ログディレクトリを作成
os.makedirs("logs", exist_ok=True)

# 日付ベースのログファイル名
log_file = f"logs/taco_{datetime.now().strftime('%Y%m%d')}.log"

# ロギングを設定
logger = setup_logging()

if __name__ == "__main__":
    settings = get_settings()
    logger.info(f"Starting TACO with log level: {settings.log_level}")
    
    # Check for configuration issues
    issues = settings.validate_configuration()
    if issues:
        for key, message in issues.items():
            logger.warning(f"Configuration issue: {key} - {message}")
    
    # Start the FastAPI application
    uvicorn.run(
        "taco.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )