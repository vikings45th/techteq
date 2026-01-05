# Python 3.11 を使用
FROM python:3.11-slim

WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコピー
COPY app.py .

# Cloud Run 標準ポート
ENV PORT=8080
EXPOSE 8080

# 起動コマンド
CMD ["python", "app.py"]
