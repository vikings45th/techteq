from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション設定クラス（環境変数から読み込み）"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Ranker ベースURL（パス無し）。Cloud Run IAM の audience 兼リクエスト先。
    RANKER_URL: str = "https://ranker-203786374782.asia-northeast1.run.app"
    REQUEST_TIMEOUT_SEC: float = 10.0  # 一般的なリクエストのタイムアウト（秒）
    RANKER_TIMEOUT_SEC: float = 10.0  # Ranker APIのタイムアウト（秒）
    LOG_LEVEL: str = "INFO"  # ログレベル（INFO/DEBUG/WARNING）

    # Google Maps Platform
    MAPS_API_KEY: str = ""  # Google Maps APIキー
    MAPS_ROUTES_BASE: str = "https://routes.googleapis.com/directions/v2:computeRoutes"  # Routes APIエンドポイント
    MAPS_PLACES_BASE: str = "https://places.googleapis.com/v1/places:searchNearby"  # Places APIエンドポイント

    # Vertex AI
    VERTEX_PROJECT: str = ""  # GCPプロジェクトID
    VERTEX_LOCATION: str = "us-central1"  # Vertex AIのリージョン（gemini-2.5-flash-lite 安定動作のため us-central1 を推奨）
    VERTEX_TEXT_MODEL: str = "gemini-2.5-flash-lite"  # 使用するLLMモデル名（短縮名を正とする。google/ プレフィックスは付けない）
    VERTEX_TEMPERATURE: float = 0.3  # LLMの温度パラメータ（0.0-1.0、低いほど一貫性が高い）
    VERTEX_MAX_OUTPUT_TOKENS: float = 256  # 最大出力トークン数
    VERTEX_TOP_P: float = 0.95  # Top-pサンプリングパラメータ
    VERTEX_TOP_K: int = 40  # Top-kサンプリングパラメータ
    VERTEX_FORBIDDEN_WORDS: str = ""  # 禁止ワード（カンマ区切り）

    # Places API（コスト最適化）
    PLACES_RADIUS_M: int = 300  # 検索半径（m）
    PLACES_MAX_RESULTS: int = 2  # 1地点あたりの最大件数
    PLACES_SAMPLE_POINTS_MAX: int = 1  # 検索地点数（サンプル点の上限）
    PLACES_NAME_BLOCKLIST: str = (
        "セブン-イレブン,ファミリーマート,ローソン,ミニストップ,"
        "マクドナルド,モスバーガー,バーガーキング,ケンタッキー,"
        "サブウェイ,ミスタードーナツ,スターバックス,ドトール,タリーズ,コメダ珈琲,"
        "すき家,吉野家,松屋,なか卯,丸亀製麺,はなまるうどん,日高屋,サイゼリヤ,ガスト"
    )
    PLACES_TYPE_BLOCKLIST: str = "convenience_store,fast_food_restaurant"

    # ルート生成（逐次生成/早期終了）
    MAX_ROUTES: int = 5  # 最大生成本数
    MIN_ROUTES: int = 2  # 最低生成本数
    SCORE_THRESHOLD: float = 0.6  # 早期終了の閾値（暫定）
    CONCURRENCY: int = 2  # 外部APIの並列数
    ROUTE_DISTANCE_ERROR_RATIO_MAX: float = 0.3  # 目標距離の許容誤差比率
    ROUTE_DISTANCE_RETRY_MAX: int = 1  # 距離フィルタ後の再生成回数
    SHORT_DISTANCE_TARGET_RATIO: float = 0.7  # 短距離時の事前距離補正比率（配布確認用コメント）
    SHORT_DISTANCE_MAX_KM: float = 3.0  # 短距離補正の上限距離（km）

    # BigQuery
    BQ_DATASET: str = "firstdown_mvp"  # BigQueryデータセット名
    BQ_TABLE_REQUEST: str = "route_request"  # リクエストテーブル名
    BQ_TABLE_CANDIDATE: str = "route_candidate"  # 候補テーブル名
    BQ_TABLE_PROPOSAL: str = "route_proposal"  # 提案テーブル名
    BQ_TABLE_FEEDBACK: str = "route_feedback"  # フィードバックテーブル名

    # 特徴量/バージョニング
    FEATURES_VERSION: str = "mvp_v1"  # 特徴量のバージョン（モデルの互換性管理用）
    RANKER_VERSION: str = "rule_v1"  # Rankerのバージョン（モデル/ロジックの追跡用）

    # ルート近傍の見どころ抽出
    SPOT_MAX_DISTANCE_M: float = 30.0  # ルートからの最大距離（m）
    SPOT_MAX_DISTANCE_M_RELAXED: float = 60.0  # 緩和時の最大距離（m）
    SPOT_MAX_DISTANCE_M_FALLBACK: float = 120.0  # 追加緩和時の最大距離（m）

    # /route/generate インプロセスTTLキャッシュ（同一条件の連続リクエストで即時レスポンス）
    GENERATE_CACHE_ENABLED: bool = True
    GENERATE_CACHE_TTL_SEC: float = 120.0
    GENERATE_CACHE_MAXSIZE: int = 256
    GENERATE_CACHE_ROUND_LATLNG_DECIMALS: int = 5
    GENERATE_CACHE_ROUND_DISTANCE_DECIMALS: int = 1


settings = Settings()  # グローバル設定インスタンス
