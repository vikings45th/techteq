from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション設定クラス（環境変数から読み込み）"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Ranker内部URL（Cloud Run内部イングレスサービスURL）
    RANKER_URL: str = "http://ranker:8080"  # RankerサービスのURL
    REQUEST_TIMEOUT_SEC: float = 10.0  # 一般的なリクエストのタイムアウト（秒）
    RANKER_TIMEOUT_SEC: float = 10.0  # Ranker APIのタイムアウト（秒）

    # Google Maps Platform
    MAPS_API_KEY: str = ""  # Google Maps APIキー
    MAPS_ROUTES_BASE: str = "https://routes.googleapis.com/directions/v2:computeRoutes"  # Routes APIエンドポイント
    MAPS_PLACES_BASE: str = "https://places.googleapis.com/v1/places:searchNearby"  # Places APIエンドポイント

    # Vertex AI
    VERTEX_PROJECT: str = ""  # GCPプロジェクトID
    VERTEX_LOCATION: str = "asia-northeast1"  # Vertex AIのリージョン
    VERTEX_TEXT_MODEL: str = "gemini-2.5-flash"  # 使用するLLMモデル名
    VERTEX_TEMPERATURE: float = 0.3  # LLMの温度パラメータ（0.0-1.0、低いほど一貫性が高い）
    VERTEX_MAX_OUTPUT_TOKENS: float = 256  # 最大出力トークン数
    VERTEX_TOP_P: float = 0.95  # Top-pサンプリングパラメータ
    VERTEX_TOP_K: int = 40  # Top-kサンプリングパラメータ

    # BigQuery
    BQ_DATASET: str = "firstdown_mvp"  # BigQueryデータセット名
    BQ_TABLE_REQUEST: str = "route_request"  # リクエストテーブル名
    BQ_TABLE_CANDIDATE: str = "route_candidate"  # 候補テーブル名
    BQ_TABLE_PROPOSAL: str = "route_proposal"  # 提案テーブル名
    BQ_TABLE_FEEDBACK: str = "route_feedback"  # フィードバックテーブル名

    # 特徴量/バージョニング
    FEATURES_VERSION: str = "mvp_v1"  # 特徴量のバージョン（モデルの互換性管理用）
    RANKER_VERSION: str = "rule_v1"  # Rankerのバージョン（モデル/ロジックの追跡用）


settings = Settings()  # グローバル設定インスタンス
