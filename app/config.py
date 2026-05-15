from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    database_url: str
    upload_dir: str = "./uploads"
    max_upload_size: int = 10485760
    allowed_extensions: List[str] = ["jpg", "jpeg", "png", "pdf", "webp", "avi"]
    ocr_api_key: str = ""
    ocr_timeout: int = 30
    redis_url: str = "redis://localhost:6379"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()