# Mostbet Cash API integration status

The API client is implemented from the supplied `Mostbet Cash API — Agent FAQ` PDF.

## Implemented API methods
- Signed request builder using HMAC SHA3-256 over `API_KEY + PATH + minified JSON body + UTC timestamp`.
- Cashpoint balance (`GET /mbc/gateway/v1/api/cashpoint/{id}/balance`).
- Player name/existence lookup (`GET .../player/name?brandId=1&clientId=...`).
- Deposit creation (`POST .../player/deposit`) with `X-Project: MBC`.
- Transaction history/status reconciliation (`GET /mbc/gateway/v2/api/cashpoint/{id}/transactions/list/all`).
- Cashout request listing and cashout confirmation methods. Cashout confirmation requires the provider transaction ID and its SMS code.
- Final success is only `COMPLETED`. `NEW`, `ACCEPTED`, and `PROCESSING` are not treated as success.
- Financial POST requests are not retried after a timeout; ambiguous results require transaction-history reconciliation to prevent duplicate operations.

## Safety defaults
`MOSTBET_LIVE_DEPOSITS_ENABLED=false` by default. Deposits are blocked until explicitly enabled. The requested configuration is `MOSTBET_CURRENCY=UZS`, but the supplied FAQ examples show USD/RUB and do not confirm UZS availability for this cashpoint. Before any live deposit, Mostbet Cash support/account settings must confirm UZS is enabled. The code checks the currency returned by the cashpoint balance endpoint and blocks the financial POST if it does not match `UZS`.

## Important boundary
Automated tests mock the HTTP responses. The supplied FAQ says the API has no sandbox, so the repository cannot prove credentials, account permissions, cashpoint currency/limits, provider-side processing, or actual money movement without a controlled live verification by the account holder. Do not describe this integration as production-verified until that test succeeds.

The bot's existing card-withdrawal flow (user submits a code and card number, then an admin processes it) is not the same process as Mostbet Cash API cashout confirmation. The API confirmation method is intentionally not connected to that existing flow because it requires a Mostbet cashout transaction ID and SMS code.

## Read-only credential/currency preflight

Before considering a controlled live test, run this script from the repository root in an environment where the credentials are set as environment variables:

```bash
python tools/mostbet_preflight.py
```

Optionally pass a provider test player ID to check player lookup as well:

```bash
python tools/mostbet_preflight.py YOUR_TEST_PLAYER_ID
```

This script only calls the cashpoint balance endpoint and, optionally, player lookup. It never sends a deposit or payout and does not print secrets or the cashpoint balance amount. A successful preflight verifies only that the read-only API calls succeeded and the cashpoint reports UZS; it does not prove a live financial transaction will succeed.

Do not enable `MOSTBET_LIVE_DEPOSITS_ENABLED` until credentials, API permissions, player lookup, amount limits, and the bot's payment reconciliation flow have been reviewed. Since the supplied documentation says there is no sandbox, any live deposit test must be explicitly authorized by the account holder and use a controlled minimal amount with a clear reconciliation plan.
