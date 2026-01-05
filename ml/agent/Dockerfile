FROM python:3.11-slim

WORKDIR /app

# pip を最新にアップグレードしてから依存関係をインストール
COPY requirements.txt .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY app.py .

# ポート指定
EXPOSE 8080

# コンテナ起動コマンド
CMD ["python", "app.py"]
