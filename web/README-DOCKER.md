# Dockerでの実行方法

## 前提条件
- Docker Desktop（Windowsの場合）がインストールされていること
- Dockerとdocker-composeコマンドが使用可能なこと

## 実行方法

### 方法1: docker-composeを使用（推奨）

```bash
cd firstdown/web
docker-compose up --build
```

バックグラウンドで実行する場合:
```bash
docker-compose up -d --build
```

停止する場合:
```bash
docker-compose down
```

### 方法2: dockerコマンドを直接使用

```bash
cd firstdown/web

# イメージをビルド
docker build -t firstdown-web .

# コンテナを実行
docker run -p 3000:3000 firstdown-web
```

## アクセス
アプリケーションは http://localhost:3000 でアクセスできます。

## 関連
本番の GCP リソース（Cloud Run 等）の定義は [infra/README.md](../infra/README.md) を参照してください。

