"""Configuración de la app: todo sale de variables de entorno (.env)."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo (en la imagen Docker es /app, que replica la misma estructura).
# Así .env y SEED_FILE funcionan igual sin importar desde qué carpeta se ejecute.
RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    # Relativo a la raíz del repo, o absoluto (ej. un archivo secreto montado en producción)
    seed_file: Path = RAIZ / "seeds" / "demo.json"

    # Base de datos
    database_url: str = "postgresql+psycopg://heladeria:heladeria@localhost:5432/heladeria"

    # WhatsApp Cloud API
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    wa_verify_token: str = ""
    wa_app_secret: str = ""
    staff_phones: str = ""  # números del personal separados por coma

    # IA
    ia_provider: str = "gemini"
    ia_model: str = ""
    ia_api_key: str = ""
    ia_base_url: str = ""  # opcional: otra URL compatible con OpenAI (ej. Ollama desde Docker)
    ia_timeout: float = 20.0  # segundos
    # Opcional: "none" apaga el razonamiento de modelos que piensan antes de responder
    # (ej. gemma4 en Ollama: de 150 s a 17 s por mensaje). Vacío = lo que use el proveedor.
    ia_reasoning_effort: str = ""

    # Límites
    web_chat_max_msgs_per_session: int = 20

    @field_validator("seed_file")
    @classmethod
    def _seed_relativo_a_la_raiz(cls, ruta: Path) -> Path:
        return ruta if ruta.is_absolute() else RAIZ / ruta

    @property
    def staff_phone_list(self) -> list[str]:
        return [p.strip() for p in self.staff_phones.split(",") if p.strip()]


settings = Settings()
