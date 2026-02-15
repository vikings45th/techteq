from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Rankerアプリケーション設定クラス（環境変数から読み込み）"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MODEL_VERSION: str = "unknown"  # モデルバージョン（影響確認用）
    MODEL_INFERENCE_MODE: str = ""  # vertex / xgb / stub / disabled（空ならMODEL_SHADOW_MODEへフォールバック）
    MODEL_SHADOW_MODE: str = "xgb"  # vertex / xgb / stub / disabled
    MODEL_TIMEOUT_S: float = 5.0  # 推論タイムアウト（秒）
    MODEL_PATH: str = "models/model.xgb.json"  # XGBoost成果物パス
    MODEL_FEATURES_PATH: str = "models/feature_columns.json"  # 特徴量カラム定義
    RANKER_VERSION: str = "unknown"  # ルール版のバージョン

    # Vertex AI Endpoint
    VERTEX_PROJECT: str = ""
    VERTEX_LOCATION: str = "asia-northeast1"
    VERTEX_ENDPOINT_ID: str = ""
    VERTEX_TIMEOUT_S: float = 10.0  # Vertex predict タイムアウト。5秒でタイムアウトしていたため延長

    BQ_PROJECT: str | None = None
    BQ_DATASET: str = "firstdown_mvp"
    BQ_RANK_RESULT_TABLE: str = "rank_result"


settings = Settings()  # グローバル設定インスタンス
