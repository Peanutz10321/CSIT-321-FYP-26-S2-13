import os
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = ".env.test" if os.getenv("APP_ENV") == "test" else ".env"


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    KEYSTORE_MASTER_SECRET: str
    # Keys the ballot commitment returned on every receipt. Deliberately separate
    # from JWT_SECRET and KEYSTORE_MASTER_SECRET so receipt signing can be rotated
    # without invalidating sessions or losing access to election private keys.
    # No default: a predictable value would let anyone forge a commitment.
    RECEIPT_SIGNING_SECRET: str
    TESTING: bool = False

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    @model_validator(mode="after")
    def validate_receipt_signing_secret(self):
        secret = self.RECEIPT_SIGNING_SECRET

        if len(secret.encode("utf-8")) < 32:
            raise ValueError("RECEIPT_SIGNING_SECRET must be at least 32 bytes")

        if secret in {self.JWT_SECRET, self.KEYSTORE_MASTER_SECRET}:
            raise ValueError(
                "RECEIPT_SIGNING_SECRET must be different from JWT_SECRET "
                "and KEYSTORE_MASTER_SECRET"
            )

        return self


settings = Settings()
