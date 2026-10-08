import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    fit_dir: Path
    # Build de l'interface web (servi par FastAPI s'il existe).
    web_dir: Path
    # Clé de chiffrement des jetons Garmin. La perdre oblige chacun à reconnecter son compte Garmin.
    secret_key: str | None
    # À activer seulement si l'app est servie en HTTPS (sinon le navigateur n'enverra pas le cookie).
    cookie_secure: bool
    # Serveur LLM compatible OpenAI (Ollama ou llama.cpp server).
    llm_base_url: str
    llm_model: str
    llm_timeout_s: float


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("COACH_DATA_DIR", "data"))
    return Settings(
        data_dir=data_dir,
        db_path=Path(os.environ.get("COACH_DB_PATH", data_dir / "coach.sqlite")),
        fit_dir=Path(os.environ.get("COACH_FIT_DIR", data_dir / "fit")),
        web_dir=Path(os.environ.get("COACH_WEB_DIR", "web/dist")),
        secret_key=os.environ.get("COACH_SECRET_KEY") or None,
        cookie_secure=os.environ.get("COACH_COOKIE_SECURE", "false").lower() == "true",
        llm_base_url=os.environ.get("COACH_LLM_BASE_URL", "http://localhost:11434"),
        llm_model=os.environ.get("COACH_LLM_MODEL", "qwen2.5:3b"),
        # Le J4125 n'a pas d'AVX : l'évaluation du prompt est lente, on laisse de la marge.
        llm_timeout_s=float(os.environ.get("COACH_LLM_TIMEOUT_S", "600")),
    )
