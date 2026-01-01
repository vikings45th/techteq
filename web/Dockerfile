# ビルドステージ
FROM node:22.16.0-alpine AS builder

WORKDIR /app

# npmのバージョンを指定
RUN npm install -g npm@10.9.2

# パッケージファイルをコピー
COPY package.json package-lock.json ./

# 依存関係をインストール
RUN npm ci

# アプリケーションのソースコードをコピー
COPY . .

# アプリケーションをビルド
RUN npm run build

# プロダクションステージ
FROM node:22.16.0-alpine AS runner

WORKDIR /app

# npmのバージョンを指定
RUN npm install -g npm@10.9.2

# プロダクション用に環境変数を設定
ENV NODE_ENV=production

# パッケージファイルをコピーしてプロダクション依存関係のみをインストール
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# ビルド成果物をコピー
COPY --from=builder /app/.output ./.output

# ポートを公開（Nuxtのデフォルトポート3000）
EXPOSE 3000

# アプリケーションを起動
CMD ["node", ".output/server/index.mjs"]

