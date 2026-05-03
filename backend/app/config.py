import os
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = ".env.test" if os.getenv("APP_ENV") == "test" else ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    TESTING: bool = False

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


settings = Settings()