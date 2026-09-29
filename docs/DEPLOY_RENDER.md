# Render free-tier deployment

The repo has a `render.yaml` Blueprint for one Docker web service and one free PostgreSQL database. This has not been called production-ready or always-on. The app deliberately runs one backend replica with SQL persistence and public market data only.

1. Sign into Render, link the owner GitHub account, and grant its GitHub app access to `ByteB1itz420/paper-trading-engine`. If GitHub consent is disabled, stop and complete authorization from the account owner device; do not bypass it.
2. Select **New → Blueprint** and choose this repository and `render.yaml`. Inspect both proposed resources: `paper-trading-engine` as a **Free** Docker web service; `paper-trading-db` as **Free** PostgreSQL. If the UI proposes a paid plan or asks for a card, stop rather than accepting.
3. The Blueprint sets `MODE=live`, generates a secret `CONTROL_TOKEN`, and attaches the database connection string. Keep the token in Render's secret settings. One web replica only. Use Render's same-region internal database URL; never expose it to the browser.
4. Deploy. Open the exact URL Render returns; verify `/health` says `connected: true` after startup, `/api/market` has BTCUSDT and ETHUSDT with fresh timestamps, the dashboard header says **LIVE PUBLIC MARKET DATA**, `/ws` yields changing quotes, and a demo run on a separate local instance remains labeled demo. Check the public dashboard on desktop and mobile. No live P&L result should be claimed until observed on the deployed service.
5. The control field requires the private token. Test kill and reset only as the owner, then clear the browser tab's session storage. A public viewer has read-only access. Keep the repo private until the owner has explicitly chosen a public release.

## Free-tier caveats

[Render's free-tier policy](https://render.com/docs/free) says a free web service spins down after 15 minutes without inbound traffic, and a first load can take around a minute. A free PostgreSQL database expires after 30 days, with a further 14-day upgrade grace period before deletion. This setup cannot supply continuous 24/7 market watching, durable interview records, or a guaranteed awake link. A live WebSocket viewer may keep the service awake during the viewing window; without one, a new backend process starts a **new** paper session after sleep. For an always-on, durable link later, move to an owner-approved paid plan and database with backups. Never infer payment approval from this document.

If Render signup or the repository grant is blocked, run locally with the README instructions. No made-up deployment URL should be used.
