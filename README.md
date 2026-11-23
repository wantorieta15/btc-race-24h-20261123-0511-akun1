# Dip-Bounce cbBTC Bot — make.fun bounty btc-race-24h-20261123-0511

[![Competition](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511)
[![Rank](https://make.fun/badge/btc-race-24h-20261123-0511/wantorieta15/btc-race-24h-20261123-0511-akun1/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511)
[![Reward](https://make.fun/badge/btc-race-24h-20261123-0511/wantorieta15/btc-race-24h-20261123-0511-akun1/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511)

A BTC trading bot for the [make.fun bounty "Race a BTC trading bot live for 24 hours"](https://make.fun/bounty/btc-race-24h-20261123-0511) ($50). It trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute bars, starting from $1,000 USDC, long only.

## Strategy

Winner formula from the previous run (btc-race-24h-20261118-1444, 3,661 entries): the top 10 all made only 1–2 full-size round trips, buying one deep washout after the bounce confirmed and selling as it recovered (PnL +1.69% to +2.16%). This bot does the same:

- **Sit in cash** most of the window.
- **Entry — buy 100% of equity, once per washout**, only when all of these hold on a bar's close:
  - close is at least **1.0% below the high of the 20 bars before it** (deep washout, not a small dip),
  - **RSI(14, Wilder) < 30** (extremely oversold),
  - close is **below the lower Bollinger band** (20 typical prices, 2 sigma),
  - bounce confirmed: **two rising closes in a row**.
- **Exit — sell the whole position** when the position is worth **+1.5% over cost**, or **RSI > 65**, or **−1.0% under cost**, whichever comes first.
- **At most 2 round trips** per window, with a 30-bar cooldown after each; then sit in cash.
- One order per reply, max slippage 100 bps, never trades while warming up.

Fully deterministic: no clock, no randomness, no network, no files outside the repo. Python 3.13, standard library only; the `vendor/makefun_bars.py` shim is a byte-for-byte copy of the kit SDK.

## Files

- `main.py` — the bot (entrypoint)
- `vendor/makefun_bars.py` — kit SDK shim (byte-for-byte copy, excluded from authorship)
- `LICENSE` — MIT
