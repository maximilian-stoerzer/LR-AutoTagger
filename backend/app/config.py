from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql://user:password@localhost:5432/lr_autotag"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llava:13b"
    ollama_max_concurrent: int = 2
    ollama_timeout: int = 120

    # API Security
    api_key: str = "change-me-to-a-random-secret"

    # Image Processing
    image_max_side: int = 1024
    batch_chunk_size: int = 50
    max_keywords: int = 25
    max_retry_attempts: int = 3

    # Nominatim
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "lr-autotag/1.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
