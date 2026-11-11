# GitHub Intelligence Bot

An asynchronous Telegram bot that retrieves GitHub user and repository information.

## Features

- `/user <username>` — show public GitHub profile information.
- `/repo <owner>/<repository>` — show repository statistics.
- Async GitHub API client using HTTPX.
- In-memory TTL cache for successful object responses.
- GitHub rate-limit and HTTP error classification.
- SQLite storage for Telegram users.
- Logging to console and `logs/bot.log`.
- Automated tests with HTTPX MockTransport.

## Requirements

- Python 3.11+
- A Telegram bot token from BotFather.
- Optional GitHub Personal Access Token.

## Setup (Windows PowerShell)

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and add your own tokens. Never commit `.env`.

## Run

```powershell
python main.py
```

## Test and lint

```powershell
python -m pytest -v
python -m ruff check .
```

## Configuration

| Variable | Default | Description |
|---|---:|---|
| `BOT_TOKEN` | required | Telegram bot token |
| `GITHUB_TOKEN` | optional | GitHub personal access token |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub API base URL |
| `GITHUB_TIMEOUT` | `15` | HTTP timeout in seconds |
| `GITHUB_CACHE_TTL` | `300` | Cache lifetime in seconds; `0` disables cache |
| `GITHUB_CACHE_MAX_ENTRIES` | `256` | Maximum cache entries |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Security

- Keep credentials only in local `.env`.
- Keep `.env` out of version control.
- `.env.example` must contain placeholders only.
- If a token is exposed, revoke it and create a replacement.
