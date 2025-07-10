#!/bin/bash

# BASE_DATEを本日日付に自動設定
BASE_DATE=$(date +"%Y-%m-%d")

# 基準日から過去1週間分の日付をループ (BASE_DATEから6日前まで)
for i in $(seq 6 -1 0); do
    # BASE_DATEからi日前の日付を計算（Linux向けdateコマンド）
    TARGET_DATE=$(date -d "${BASE_DATE} -${i} day" +"%Y-%m-%d")
    echo "Fetching messages for ${TARGET_DATE} and saving to raw JSON..."

    # main.pyを実行し、その出力をJSONファイルに保存
    OUTPUT_FILE="reports/raw/raw_messages_${TARGET_DATE}.json"
    python3 main.py "${TARGET_DATE}" > "${OUTPUT_FILE}"

    if [ -s "${OUTPUT_FILE}" ]; then
        echo "Raw messages saved to ${OUTPUT_FILE}"
    else
        echo "No messages found for ${TARGET_DATE}. ${OUTPUT_FILE} might be empty or not created."
    fi
done

# tasks.mdの更新は、Gemini CLIがレポート生成時に行うため、ここでは行いません。
# もしGemini CLIがtasks.mdを更新しない場合は、手動で最新のレポートから抽出してください。