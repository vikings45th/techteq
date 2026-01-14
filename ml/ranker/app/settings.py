from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Rankerアプリケーション設定クラス（環境変数から読み込み）"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MODEL_VERSION: str = "stub_v1"  # モデルバージョン（現在はスタブ実装）


settings = Settings()  # グローバル設定インスタンス
