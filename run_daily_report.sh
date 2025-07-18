#!/bin/bash

# 日次レポートを手動で実行するスクリプト

# スクリプトのディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# アプリケーションのルートディレクトリに移動
cd "$SCRIPT_DIR"

# 日次レポートを実行
echo "Triggering daily report..."
curl -X POST http://localhost:8000/trigger/daily-report

echo "Done!"