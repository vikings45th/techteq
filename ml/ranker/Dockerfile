# ベースイメージを Python 3.11 に変更
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 依存関係をコピー
COPY requirements.txt .

# pip を最新にアップグレードしてから依存関係をインストール
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY app.py .

# デフォルトコマンド
CMD ["python", "app.py"]
