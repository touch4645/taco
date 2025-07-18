#!/usr/bin/env python
"""
週次レポート生成スクリプト
"""
import os
import sys
import logging
import requests
from datetime import datetime, timedelta

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    """
    週次レポートを生成
    """
    logger.info("週次レポートの生成を開始します...")
    
    # APIエンドポイントを呼び出し
    try:
        response = requests.post("http://localhost:8000/trigger/weekly-report")
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"週次レポートの生成が完了しました: {result}")
        
        # 結果を表示
        print(f"週次レポート生成結果:")
        print(f"状態: {result.get('status')}")
        print(f"期間: {result.get('week_start')} - {result.get('week_end')}")
        print(f"完了率: {result.get('completion_rate'):.1f}%")
        print(f"主要な成果: {result.get('key_achievements')} 件")
        print(f"ブロッカー: {result.get('blockers')} 件")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"APIリクエスト中にエラーが発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()