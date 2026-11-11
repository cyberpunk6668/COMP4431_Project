"""Server-only configuration. Credentials never enter API responses."""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""), repr=False)
    model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-flash"))
    timeout: float = field(default_factory=lambda: float(os.getenv("DEEPSEEK_TIMEOUT", "45")))
    offline: bool = field(default_factory=lambda: os.getenv("FINPILOT_OFFLINE", "false").lower() == "true")
    db_path: Path = field(default_factory=lambda: Path(os.getenv("FINPILOT_DB", str(ROOT / "data" / "finpilot.sqlite3"))))
    knowledge_path: Path = ROOT / "data" / "knowledge.json"
    adapter_path: Path = field(default_factory=lambda: Path(os.getenv("FINPILOT_ADAPTER", str(ROOT / "models" / "finpilot-lora"))))
    ml_python: Path = field(default_factory=lambda: Path(os.getenv("FINPILOT_ML_PYTHON", str(ROOT / ".venv-ml" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))))
    hf_home: str = field(default_factory=lambda: os.getenv("FINPILOT_HF_HOME", ""))
    local_timeout: float = 60

    @property
    def online(self) -> bool:
        return bool(self.api_key.strip()) and not self.offline
