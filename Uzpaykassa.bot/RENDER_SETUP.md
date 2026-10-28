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

## Mostbet Cash API configuration
Set these values in Render → Environment (never commit them to GitHub):
- `MOSTBET_API_KEY`: the full key including the documented `api-key:` prefix
- `MOSTBET_API_SECRET`: the signing secret
- `MOSTBET_CASHPOINT_ID`: your verified cashpoint ID
- `MOSTBET_CURRENCY`: set to `UZS` for the requested configuration only after Mostbet Cash confirms UZS is enabled for this cashpoint; the code compares this setting with the currency returned by the balance endpoint and blocks deposits on mismatch
- `MOSTBET_LIVE_DEPOSITS_ENABLED`: keep `false` until account access, currency, limits, and the signing configuration have been verified; set `true` only for a controlled live test after you accept that the documentation says there is no sandbox
- `MOSTBET_API_BASE_URL`: optional, defaults to `https://apimb.com`
- `MOSTBET_API_TIMEOUT`: optional, defaults to `15` seconds
- `MOSTBET_STATUS_POLL_SECONDS`: optional, defaults to `3`
- `MOSTBET_STATUS_POLL_ATTEMPTS`: optional, defaults to `8`

The integration follows the supplied Mostbet Cash API FAQ: HMAC SHA3-256 signature, UTC timestamp, `X-Api-Key`, `X-Timestamp`, `X-Signature`, `X-Project: MBC` on financial POST requests, player lookup, balance, deposit creation, and transaction-history status reconciliation. A deposit is reported successful only for final `COMPLETED` status. The code does not automatically retry a financial POST after a timeout; uncertain results are sent for operator reconciliation to avoid duplicate deposits.

## Important production boundary
- Automated tests use mocked API responses; they do not contact Mostbet or move money.
- The supplied FAQ says there is no sandbox. A real API call must only be attempted after the cashpoint account is verified and currency/limits are confirmed. Start with a controlled, low-value live test and reconcile it in Mostbet Cash transaction history.
- The bot's existing card-withdrawal workflow is not the same as Mostbet Cash API cashout confirmation. The API method requires a Mostbet cashout `transactionId` plus its SMS confirmation code; it is intentionally not triggered by the bot's current 4-digit code/card-number flow.
- 1xBet, Melbet, Betwiner, and WinWinBet adapters remain disabled/placeholders.
- A local SQLite database without a persistent disk may be lost on redeploy/restart.

## Persistent database (required before production)
1. In Render, add a **Persistent Disk** to this Web Service and mount it at `/var/data`.
2. Set `DATABASE_PATH=/var/data/bot_database.db` in Environment.
3. Redeploy, then verify the service logs show no SQLite `unable to open database file` errors.
4. Do not put a live `bot_database.db` in GitHub or in ZIP archives. Back up the mounted database securely and restrict access because it contains user and payment records.

## Current verification boundary
- The in-bot `📜 Operatsiyalar tarixi` screen shows the current user's latest deposits and withdrawal requests only. It intentionally does not display full card numbers or verification codes.
- Local automated tests do not validate real bank notifications, Telegram delivery, Render disk persistence, or bookmaker-side money movement. Those require deployment checks and official provider test credentials.
- Mostbet API request signing and response/status handling are covered by mocked tests. Actual account authorization, allowed currency, cashpoint limits, provider-side status propagation, and live funds movement remain unverified until tested with the user's authorized credentials.
