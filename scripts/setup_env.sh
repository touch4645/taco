#!/bin/bash

# TACOの環境をセットアップするスクリプト

# 必要なディレクトリを作成
mkdir -p logs
mkdir -p data

# .envファイルが存在しない場合は作成
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "Please edit .env file with your actual configuration values."
else
    echo ".env file already exists."
fi

# データベースの初期化
echo "Initializing database..."
python -m scripts.init_db

echo "Environment setup completed!"
echo "Next steps:"
echo "1. Edit .env file with your actual configuration values"
echo "2. Run 'docker-compose up -d' to start the application"