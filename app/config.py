# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    # App Identity
    APP_NAME: str = "WanderKashmir API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Azure Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_ACCOUNT_NAME: str = ""
    AZURE_STORAGE_ACCOUNT_KEY: str = ""
    AZURE_CONTAINER_DESTINATIONS: str = "destinations"
    AZURE_CONTAINER_HOTELS: str = "hotels"
    AZURE_CONTAINER_ITINERARIES: str = "itineraries"
    AZURE_CONTAINER_VEHICLES: str = "vehicles"
    AZURE_CONTAINER_QUOTATIONS: str = "quotations"

    # Pricing defaults
    DEFAULT_GST_RATE: float = 0.05
    QUOTATION_VALID_DAYS: int = 7

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"
    LOG_FILE: str = "logs/app.log"
    PDF_TEMP_DIR: str = "temp/pdfs"
    PDF_AUTO_UPLOAD: bool = True

    # Add these for the email service
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # CORS settings (accepts comma-separated string)
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()