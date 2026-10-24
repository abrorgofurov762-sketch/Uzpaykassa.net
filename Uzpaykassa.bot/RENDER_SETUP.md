# Render deployment (technical startup only)

## Service settings
- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Type: Web Service (the existing `main.py` exposes a Flask health endpoint and runs Telegram polling)

## Required Environment Variables
- `BOT_TOKEN`: a newly rotated token from @BotFather
- `ADMIN_ID`: your Telegram numeric user ID

Optional settings: `DATABASE_PATH`, `MIN_DEPOSIT`, `MAX_DEPOSIT`, `NOTIFICATION_CHANNEL_ID`, `BOT_ACTIVE`.
For a Render persistent disk, set `DATABASE_PATH` to the disk mount path, for example `/var/data/bot_database.db`, and mount a disk at `/var/data`.

## Important limitations
- This build fixes import/syntax blockers and makes configuration environment-based.
- Provider adapters are intentionally disabled and return `Success: False`. Deposit, payout, balance, and player lookup operations will not work until official provider API integrations are implemented and tested.
- Do not enable real-money use based only on this technical startup check.
- A local SQLite database without a persistent disk may be lost on redeploy/restart.
