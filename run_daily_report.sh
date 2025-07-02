#!/bin/bash

# 過去1週間分の日付をループ
for i in $(seq 6 -1 0); do
    TARGET_DATE=$(date -v -${i}d +%Y-%m-%d)
    echo "Fetching messages for ${TARGET_DATE} and saving to raw JSON..."
    .venv/bin/python main.py "${TARGET_DATE}"
done

echo "All raw message JSON files have been generated in reports/raw/."
echo "Please instruct me to process these files to generate daily reports and update tasks.md."
