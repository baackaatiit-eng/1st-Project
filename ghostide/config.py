import os
from dataclasses import dataclass


@dataclass
class Config:
    telegram_token: str = ""
    allowed_users: tuple = ()  # Telegram user ids; empty = nobody allowed
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    data_dir: str = "./data"
    sandbox_image: str = "python:3.11-slim"
    sandbox_mem: str = "512m"
    sandbox_cpus: str = "1"
    sandbox_pids: int = 128
    sandbox_timeout: int = 120
    max_repairs: int = 3
    allow_unsafe_local: bool = False

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        users = tuple(int(x) for x in e.get("GHOSTIDE_ALLOWED_USERS", "").split(",") if x.strip())
        return cls(
            telegram_token=e.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_users=users,
            llm_base_url=e.get("LLM_BASE_URL", cls.llm_base_url).rstrip("/"),
            llm_api_key=e.get("LLM_API_KEY", ""),
            llm_model=e.get("LLM_MODEL", cls.llm_model),
            data_dir=e.get("GHOSTIDE_DATA_DIR", cls.data_dir),
            sandbox_image=e.get("SANDBOX_IMAGE", cls.sandbox_image),
            sandbox_mem=e.get("SANDBOX_MEM", cls.sandbox_mem),
            sandbox_cpus=e.get("SANDBOX_CPUS", cls.sandbox_cpus),
            sandbox_timeout=int(e.get("SANDBOX_TIMEOUT", cls.sandbox_timeout)),
            max_repairs=int(e.get("MAX_REPAIRS", cls.max_repairs)),
            allow_unsafe_local=e.get("GHOSTIDE_ALLOW_UNSAFE_LOCAL") == "1",
        )

    def secrets(self):
        return [s for s in (self.telegram_token, self.llm_api_key) if s]
