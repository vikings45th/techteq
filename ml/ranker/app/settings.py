from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Rankerアプリケーション設定クラス（環境変数から読み込み）"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MODEL_VERSION: str = "unknown"  # モデルバージョン（影響確認用）
    MODEL_SHADOW_MODE: str = "xgb"  # xgb / stub / disabled
    MODEL_TIMEOUT_S: float = 5.0  # 推論タイムアウト（秒）
    MODEL_PATH: str = "models/model.xgb.json"  # XGBoost成果物パス
    MODEL_FEATURES_PATH: str = "models/feature_columns.json"  # 特徴量カラム定義
    RANKER_VERSION: str = "unknown"  # ルール版のバージョン

    BQ_PROJECT: str | None = None
    BQ_DATASET: str = "firstdown_mvp"
    BQ_RANK_RESULT_TABLE: str = "rank_result"


settings = Settings()  # グローバル設定インスタンス
