#!/bin/bash

# 引数から基準日と取得日数を設定
# $1: 基準日 (YYYY-MM-DD形式)。指定がなければ今日の日付。
# $2: 取得日数。指定がなければ7日間。
BASE_DATE=${1:-$(date -j "+%Y-%m-%d")}
DAYS_AGO=${2:-7}

# DAYS_AGOから1を引いて、seqコマンド用のループ回数を計算
# (例: 7日間の場合、0から6までループ)
LOOP_COUNT=$((DAYS_AGO - 1))

# 基準日から過去N日分の日付をループ
for i in $(seq $LOOP_COUNT -1 0); do
    # BASE_DATEからi日前の日付を計算
    TARGET_DATE=$(date -j -v -${i}d -f "%Y-%m-%d" "${BASE_DATE}" "+%Y-%m-%d")
    echo "Fetching messages for ${TARGET_DATE}..."

    # main.pyを実行
    .venv/bin/python main.py "${TARGET_DATE}"
done

# tasks.mdの更新は、Gemini CLIがレポート生成時に行うため、ここでは行いません。
# もしGemini CLIがtasks.mdを更新しない場合は、手動で最新のレポートから抽出してください。