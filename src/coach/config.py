import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    fit_dir: Path
    # Physiologie de l'athlète, utilisée pour le TRIMP (charge d'entraînement).
    hr_rest: int
    hr_max: int
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
        hr_rest=int(os.environ.get("COACH_HR_REST", "50")),
        hr_max=int(os.environ.get("COACH_HR_MAX", "185")),
        llm_base_url=os.environ.get("COACH_LLM_BASE_URL", "http://localhost:11434"),
        llm_model=os.environ.get("COACH_LLM_MODEL", "qwen2.5:3b"),
        # Le J4125 n'a pas d'AVX : l'évaluation du prompt est lente, on laisse de la marge.
        llm_timeout_s=float(os.environ.get("COACH_LLM_TIMEOUT_S", "600")),
    )
