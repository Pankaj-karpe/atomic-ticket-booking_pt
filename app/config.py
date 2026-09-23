from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str | None = None
    ALEMBIC_DB_URL: str | None = None
    SUPABASE_DB_URL: str | None = None

    #we will use python inbuild function to generate the secret_key
    SECRET_KEY: str | None = None
    ALGORITHM: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int | None = None

    REDIS_HOST: str | None = None
    REDIS_PORT: str | None = None

    RABBITMQ_HOST: str | None = None
    RABBITMQ_USER: str | None = None
    RABBITMQ_PASSWORD: str | None = None
    RABBITMQ_PORT: str | None = None

    CELERY_BROKER_URL: str | None = None
    BROKER_URL: str | None = None
    HOLD_EXPIRY_MINUTES: int | None = None
    FASTAPI_INTERNAL_URL: str | None = None

    SMTP_HOST: str | None = None
    SMTP_PORT: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    FROM_EMAIL: str | None = None
    REFUND_CUTOFF_HOURS: int | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()