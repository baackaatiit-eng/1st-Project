import os
import threading

from . import redact
from .bot import Bot
from .builder import Builder
from .config import Config
from .dashboard import make_server
from .llm import OpenAICompatible
from .sandbox import get_sandbox
from .store import Store


def main():
    cfg = Config.from_env()
    os.makedirs(cfg.data_dir, exist_ok=True)
    redact.register(*cfg.secrets())
    redact.setup_logging(os.path.join(cfg.data_dir, "ghostide.log"))
    if not cfg.telegram_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if not cfg.allowed_users:
        raise SystemExit("GHOSTIDE_ALLOWED_USERS is required (comma-separated Telegram user ids)")
    store = Store(os.path.join(cfg.data_dir, "ghostide.db"))
    llm = OpenAICompatible(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    builder = Builder(cfg, llm, get_sandbox(cfg), store)
    dtoken = os.environ.get("DASHBOARD_TOKEN", "")
    if dtoken:
        srv = make_server(store, dtoken, os.environ.get("DASHBOARD_HOST", "127.0.0.1"), int(os.environ.get("PORT", 8080)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    Bot(cfg, builder, store).poll_forever()


main()
