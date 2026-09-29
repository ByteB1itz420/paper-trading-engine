# Interview demonstration

Run `MODE=demo` for repeatable synthetic quote waves. The header says **SYNTHETIC DEMO MODE**, and all fills are paper-only. The demo generator uses fixed price waves with two outliers, not historical Binance data. It should produce a long signal, risk check, simulated fill, P&L change, and exit when the mean recovers. A short proposal is deliberately rejected in the cash-only portfolio. You can show that rejection in the risk panel.

To demonstrate the kill switch, provide the operator's `CONTROL_TOKEN` in the dashboard's local control field, select **ACTIVATE KILL SWITCH**, and observe the halted label. Future signals show manual-kill rejections. Select **Resume** to continue. **Reset session** starts a fresh virtual account while preserving prior records in SQL. Do not enter a real exchange key.

For live mode set `MODE=live`; the adapter reads two Binance Spot pairs from `data-stream.binance.vision` without credentials. The header must change to **LIVE PUBLIC MARKET DATA**. Depending on market moves, there may be no signal or trade during a short demo. Do not pass demo returns, demo screenshots, or a manufactured equity curve off as live market performance. When the WebSocket disconnects, the UI reports it and the engine rejects stale quotes.
