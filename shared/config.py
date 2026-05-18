from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_url: str = "postgresql://user:pass@db:5432/reality"
    analyzer_url: str = "http://analyzer:8081"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email: str = ""

    scrape_interval_hours: int = 6
    bargain_score_threshold: float = 70.0
    hot_offer_max_days: int = 7


settings = Settings()
