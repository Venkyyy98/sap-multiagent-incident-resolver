from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    mock_mode: bool = True
    confidence_threshold: float = 0.85
    chroma_dir: str = ".chroma"
    # Circuit breaker: autonomously stop a flow (no human click) once a contain-the-damage root
    # cause (cert/credential/bad-payload) has failed repeatedly. Threshold guards against tripping
    # on a single transient blip. Set auto_stop_enabled=false to require a human for every stop.
    auto_stop_enabled: bool = True
    auto_stop_failure_threshold: int = 3
    auto_stop_lookback_hours: int = 24
    # Background poller: automatically refreshes data/live_incidents.json from the live tenant on
    # a timer, instead of requiring a manual `python -m connectors.sap_cpi` run.
    poll_enabled: bool = True
    poll_interval_seconds: int = 90

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
