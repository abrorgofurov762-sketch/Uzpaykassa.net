# Uzpaykassa Telegram bot

## Important status
This repository is prepared for GitHub upload and controlled deployment checks. It is **not yet verified for production real-money use**. Automated tests use mocked API responses; they do not prove that the live Mostbet account accepts requests or that money moves correctly. Do not enable live deposits until the read-only preflight succeeds and you have reviewed the live-operation risks.

## Project files
The project files are at the repository root. `main.py` starts the Telegram bot and a small Flask health endpoint. `main_optimized.py` is retained as an alternate implementation; use only `main.py` as the Render start command unless you deliberately validate the alternate.

## Local setup
1. Use Python 3.11 or 3.12.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` for local development, then set the required values. Never commit `.env` or real credentials.
4. Run tests: `python -m unittest discover -s tests -v`.
5. Run the bot: `python main.py`.

## Render setup
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Required environment variables: `BOT_TOKEN`, `ADMIN_ID`
- Add a persistent disk mounted at `/var/data` and set `DATABASE_PATH=/var/data/bot_database.db`.
- Set Mostbet credentials only in Render Environment: `MOSTBET_API_KEY`, `MOSTBET_API_SECRET`, `MOSTBET_CASHPOINT_ID`.
- Keep `MOSTBET_LIVE_DEPOSITS_ENABLED=false` until all read-only checks and authorized live verification are complete.

## Mostbet read-only preflight
Set the credentials in the environment (never on the command line or in source control), then run:

```bash
python tools/mostbet_preflight.py
```

Optional player lookup:

```bash
python tools/mostbet_preflight.py YOUR_TEST_PLAYER_ID
```

This tool performs read-only balance and optional player lookup calls. It does not deposit or withdraw money. A successful preflight only verifies that the live account responds and the currency returned by the cashpoint matches `MOSTBET_CURRENCY`; it does not prove live deposits are safe or successful.

## Important integration boundaries
- Mostbet API request signing, deposit request construction, and transaction-history reconciliation have automated mock tests. Real credentials, access rights, transaction limits, UZS support for this exact cashpoint, and actual money movement must still be verified with the account holder and provider.
- The provider documentation supplied for this project says no sandbox is available. Do not run an unapproved live test.
- A timed-out financial POST is ambiguous and must be reconciled against transaction history; do not retry it automatically.
- The existing user card-withdrawal workflow is not the same as confirming a Mostbet cashout request. Mostbet cashout confirmation requires a provider transaction ID and its confirmation code.
- 1xBet, Melbet, Betwiner, and WinWinBet adapters are placeholders/disabled. They are not production integrations.
- Bank payment detection relies on incoming notification message formats and must be verified against real notification samples. Ambiguous matches should be manually reviewed.
- Before production use, review local legal/regulatory requirements, payment-provider terms, access control, data retention, backup, and operational reconciliation procedures.

## Security
- Never commit `.env`, API secrets, bot tokens, database files, logs, or personal payment records.
- If any secret was ever committed to a repository or sent in a chat, rotate it.
- Keep a secure backup of the persistent database and limit access to it.
