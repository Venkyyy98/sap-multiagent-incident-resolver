from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    mock_mode: bool = True
    confidence_threshold: float = 0.85
    chroma_dir: str = ".chroma"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
