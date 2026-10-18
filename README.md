# GhostIDE
Telegram bot (@Fo2_devBot) that turns ideas into built, tested, zipped projects. Stdlib-only Python 3.11.

## Flow
message -> LLM manifest (files + install/test/smoke commands) -> files in workspace -> sandbox runs install (network on), tests and smoke (network off) -> on failure, errors go back to the LLM (up to MAX_REPAIRS) -> ZIP only if everything passed. `/get <id>` sends it.

## Run tests
`python3 -m unittest discover -s tests -t .`

## Deploy (needs YOUR credentials; I did not do this)
1. Get the bot token from @BotFather, your user id (message the bot once; it replies with your id), and an LLM API key.
2. `cp .env.example .env` and fill in. Any OpenAI-compatible provider works via LLM_BASE_URL.
3. Host must have Docker (sandbox: no network for tests, read-only fs, cap-drop ALL, mem/cpu/pids/time limits). The bot refuses to run code without Docker.
4. `docker build -t ghostide .` then `docker run -d --restart=always --env-file .env -v /data:/data -v /var/run/docker.sock:/var/run/docker.sock ghostide`.
   Caveat: mounting the docker socket grants host-level power; prefer a dedicated VM, and note workspace paths must be host-visible (mount /data at same path).

## Security
Only GHOSTIDE_ALLOWED_USERS may use the bot. Secrets are redacted from logs/messages, are not passed into the sandbox. Deployments/purchases are never performed by the bot.

## Dashboard
Set DASHBOARD_TOKEN for a bearer-protected read-only API: /api/projects, /api/projects/<id>/builds, /api/builds/<id>/logs, /health.

## Verification status
Unit tests pass (fake LLM, unsafe local sandbox opt-in). NOT verified here: Docker sandbox (no Docker available), real Telegram, real LLM.
