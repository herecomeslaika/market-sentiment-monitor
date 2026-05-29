from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # RSS
    rss_urls: dict[str, str] = {
        "wallstreetcn": "https://wallstreetcn.com/rss",
        "cls": "https://www.cls.cn/api/rss",
    }
    rss_poll_interval_seconds: int = 30
    rss_request_timeout_seconds: int = 10

    # Dedup
    dedup_cache_max_size: int = 10000

    # Sentiment model
    model_name: str = "lxyuan/distilbert-base-multilingual-cased-sentiments-student"
    process_pool_size: int = 2

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.3
    deepseek_max_tokens: int = 2048

    # Alert thresholds
    default_alert_threshold: float = -0.5

    # SMTP (for email notifications)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SENTIMENT_")
