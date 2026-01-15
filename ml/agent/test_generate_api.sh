#!/bin/bash
# generate APIを4つのテーマでテストするbashスクリプト（curl使用）
#
# 使用方法:
#   bash test_generate_api.sh
#   または
#   ./test_generate_api.sh
#
# 環境変数:
#   AGENT_URL: APIのベースURL（デフォルト: http://localhost:8000）
#   FEEDBACK_RATING: 固定評価（未指定ならランダム 1-5）
#
# 例:
#   export AGENT_URL=https://agent-203786374782.asia-northeast1.run.app
#   bash test_generate_api.sh

set -euo pipefail

# デフォルトのAPI URL
AGENT_URL="${AGENT_URL:-http://localhost:8000}"
FEEDBACK_RATING="${FEEDBACK_RATING:-}"
ROUND_TRIPS=("true" "false")

# テーマのリスト
THEMES=("exercise" "think" "refresh" "nature")

# 東京周辺の緯度経度範囲（ランダム生成用）
TOKYO_LAT_MIN=35.0
TOKYO_LAT_MAX=36.0
TOKYO_LNG_MIN=139.0
TOKYO_LNG_MAX=140.0

# 距離の範囲（km）
DISTANCE_MIN=1.0
DISTANCE_MAX=5.0

# curlとjqが利用可能か確認
if ! command -v curl &> /dev/null; then
    echo "❌ エラー: curlがインストールされていません" >&2
    exit 1
fi

HAS_JQ=true
if ! command -v jq &> /dev/null; then
    echo "⚠️  警告: jqがインストールされていません。JSONの整形・route_id抽出ができません。" >&2
    HAS_JQ=false
    JQ_CMD="cat"
else
    JQ_CMD="jq"
fi

# ランダムな開始地点を生成
generate_random_location() {
    local lat=$(awk "BEGIN { srand(); printf \"%.6f\", $TOKYO_LAT_MIN + rand() * ($TOKYO_LAT_MAX - $TOKYO_LAT_MIN) }")
    local lng=$(awk "BEGIN { srand(); printf \"%.6f\", $TOKYO_LNG_MIN + rand() * ($TOKYO_LNG_MAX - $TOKYO_LNG_MIN) }")
    echo "$lat $lng"
}

# ランダムな距離を生成（km）
generate_random_distance() {
    awk "BEGIN { srand(); printf \"%.1f\", $DISTANCE_MIN + rand() * ($DISTANCE_MAX - $DISTANCE_MIN) }"
}

# ランダムな評価（1-5）を生成
generate_random_rating() {
    awk "BEGIN { srand(); printf \"%d\", 1 + int(rand() * 5) }"
}

# テーマと往復設定をテスト
test_theme() {
    local round_trip=$1
    local theme=$2
    local request_id="test-$(date +%s)-$RANDOM"
    
    # ランダムなパラメータを生成
    local location=$(generate_random_location)
    local lat=$(echo "$location" | cut -d' ' -f1)
    local lng=$(echo "$location" | cut -d' ' -f2)
    local distance_km=$(generate_random_distance)
    local debug=false  # 固定値
    local end_lat=""
    local end_lng=""

    if [ "$round_trip" = "false" ]; then
        local end_location=$(generate_random_location)
        end_lat=$(echo "$end_location" | cut -d' ' -f1)
        end_lng=$(echo "$end_location" | cut -d' ' -f2)
    fi
    
    echo "============================================================"
    echo "テーマ: $theme"
    echo "開始地点: ($lat, $lng)"
    echo "距離: ${distance_km}km"
    echo "往復ルート: $round_trip"
    if [ "$round_trip" = "false" ]; then
        echo "終了地点: ($end_lat, $end_lng)"
    fi
    echo "リクエストID: $request_id"
    echo "============================================================"
    
    # JSONペイロードを作成
    local json_payload=$(cat <<EOF
{
  "request_id": "$request_id",
  "theme": "$theme",
  "distance_km": $distance_km,
  "start_location": {
    "lat": $lat,
    "lng": $lng
  },
  "round_trip": $round_trip,
  "debug": $debug
}
EOF
)
    if [ "$round_trip" = "false" ]; then
        json_payload=$(cat <<EOF
{
  "request_id": "$request_id",
  "theme": "$theme",
  "distance_km": $distance_km,
  "start_location": {
    "lat": $lat,
    "lng": $lng
  },
  "end_location": {
    "lat": $end_lat,
    "lng": $end_lng
  },
  "round_trip": $round_trip,
  "debug": $debug
}
EOF
)
    fi
    
    # curlでAPIを呼び出し
    local response
    local status_code
    response=$(curl -sS -w "\n%{http_code}" -X POST "$AGENT_URL/route/generate" \
        -H "Content-Type: application/json" \
        -d "$json_payload")
    
    status_code=$(echo "$response" | tail -n1)
    response_body=$(echo "$response" | sed '$d')
    
    if [ "$status_code" -eq 200 ]; then
        echo "✅ 成功 (HTTP $status_code)"
        echo ""
        echo "$response_body" | $JQ_CMD
        echo ""

        # route_idを抽出してフィードバック送信
        if [ "$HAS_JQ" = true ]; then
            local route_id
            route_id=$(echo "$response_body" | jq -r '.route.route_id // empty')
            if [ -n "$route_id" ]; then
                local rating="${FEEDBACK_RATING:-$(generate_random_rating)}"
                echo "📝 フィードバック送信: route_id=$route_id rating=$rating"
                local feedback_payload=$(cat <<EOF
{
  "request_id": "$request_id",
  "route_id": "$route_id",
  "rating": $rating
}
EOF
)
                local feedback_response
                local feedback_status
                feedback_response=$(curl -sS -w "\n%{http_code}" -X POST "$AGENT_URL/route/feedback" \
                    -H "Content-Type: application/json" \
                    -d "$feedback_payload")
                feedback_status=$(echo "$feedback_response" | tail -n1)
                feedback_body=$(echo "$feedback_response" | sed '$d')
                if [ "$feedback_status" -eq 200 ]; then
                    echo "✅ フィードバック成功 (HTTP $feedback_status)"
                    echo "$feedback_body" | $JQ_CMD
                else
                    echo "❌ フィードバック失敗 (HTTP $feedback_status)"
                    echo "$feedback_body"
                fi
            else
                echo "⚠️  route_idが取得できませんでした。フィードバックをスキップします。"
            fi
        else
            echo "⚠️  jqがないためroute_idを取得できず、フィードバックをスキップします。"
        fi
    else
        echo "❌ エラー (HTTP $status_code)"
        echo "$response_body"
    fi
    
    echo ""
}

# メイン処理
echo "🚀 Generate API テストスクリプト"
echo "API URL: $AGENT_URL"
echo "テスト対象テーマ: ${THEMES[*]}"
echo ""

# ヘルスチェック
if ! curl -sS -f "$AGENT_URL/health" > /dev/null; then
    echo "❌ ヘルスチェックエラー: APIが起動しているか確認してください" >&2
    exit 1
fi

# 各テーマで周回/片道をテスト
for theme in "${THEMES[@]}"; do
    for round_trip in "${ROUND_TRIPS[@]}"; do
        test_theme "$round_trip" "$theme"

        # リクエスト間隔を空ける（API負荷軽減）
        sleep 1
    done
done

echo "============================================================"
echo "📋 テスト完了"
echo "============================================================"
