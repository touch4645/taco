FROM python:3.11-slim

WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ログディレクトリを作成
RUN mkdir -p logs

# 環境変数を設定
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# ポートを公開
EXPOSE 8000

# アプリケーションを実行
CMD ["uvicorn", "taco.api.app:app", "--host", "0.0.0.0", "--port", "8000"]