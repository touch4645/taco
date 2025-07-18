#!/usr/bin/env python
"""
データベースの初期化スクリプト
"""
import os
import sys
import logging

# 親ディレクトリをパスに追加して、tacoパッケージをインポートできるようにする
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from taco.utils.database import init_database
from taco.config.settings import get_settings

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    """
    データベースの初期化を実行
    """
    logger.info("データベースの初期化を開始します...")
    
    # 設定を読み込み
    settings = get_settings()
    logger.info(f"データベースURL: {settings.database_url}")
    
    # データベースを初期化
    init_database()
    
    logger.info("データベースの初期化が完了しました")

if __name__ == "__main__":
    main()