"""Dip-bounce cbBTC bot for make.fun bounty btc-race-24h-20261123-0511.

Winner formula from the previous run (btc-race-24h-20261118-1444, 3,661
entries): the top 10 all made only 1-2 full-size round trips, buying one
deep washout after the bounce had confirmed and selling as it recovered
(PnL +1.69% to +2.16%, max drawdown 0.6-1.3%). So this bot sits in cash,
buys 100% of equity exactly once per washout, and only when every one of
these holds on a bar's close:

  - the close is at least 1.0% below the high of the last 20 bars (the
    washout is deep, not one of the many small 0.5% dips),
  - RSI(14, Wilder) is below 30 (extremely oversold),
  - the close is below the lower Bollinger band (20 typical prices,
    2 sigma),
  - the bounce has confirmed: the close rises after the dip
    (close > previous close). Two rising closes in a row was tested
    and never fires on the dev window: by the second rising close
    the RSI has already recovered above 30.

It sells the whole position when the position is worth 1.5% over its
cost, or RSI rises above 65, or the position falls 1.0% under its cost,
whichever comes first. At most 2 round trips per window; after that it
sits in cash. One order per reply, max slippage 100 bps, never trades
while warming up. Fully deterministic: no clock, no randomness, no
network, no files outside the repo. Python 3.13, standard library only.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
RSI_PERIOD = 14
RSI_ENTRY_MAX = 30.0
RSI_EXIT_MIN = 65.0
BAND_BARS = 20
BAND_SIGMAS = 2.0
HIGH_BARS = 20
DIP_MIN_BPS = 100  # entry needs the close >= 1.0% below the 20-bar high
TAKE_PROFIT_BPS = 150  # exit at +1.5% over cost
STOP_LOSS_BPS = 100  # exit at -1.0% under cost
MAX_ROUND_TRIPS = 2
COOLDOWN_BARS = 30  # bars to wait after a round trip before re-entering
MAX_SLIPPAGE_BPS = 100


class _Series:
    """Per-symbol price history: closes, typical prices, Wilder RSI."""

    def __init__(self):
        self.closes = []
        self.typicals = []
        self._prev_close = None
        self._first_changes = []
        self.avg_gain = None
        self.avg_loss = None

    def push(self, bar):
        close = int(bar["c"])
        typical = (int(bar["h"]) + int(bar["l"]) + close) / 3.0
        self.closes.append(close)
        self.typicals.append(typical)
        if self._prev_close is not None:
            change = close - self._prev_close
            if self.avg_gain is None:
                self._first_changes.append(change)
                if len(self._first_changes) == RSI_PERIOD:
                    ups = sum(x for x in self._first_changes if x > 0)
                    downs = sum(-x for x in self._first_changes if x < 0)
                    self.avg_gain = ups / RSI_PERIOD
                    self.avg_loss = downs / RSI_PERIOD
            else:
                up = change if change > 0 else 0
                down = -change if change < 0 else 0
                self.avg_gain = (self.avg_gain * (RSI_PERIOD - 1) + up) / RSI_PERIOD
                self.avg_loss = (self.avg_loss * (RSI_PERIOD - 1) + down) / RSI_PERIOD
        self._prev_close = close

    def rsi(self):
        """Wilder RSI(14) on closes, or None before 14 changes exist."""
        if self.avg_gain is None or self.avg_loss is None:
            return None
        moved = self.avg_gain + self.avg_loss
        if moved == 0:
            return 50.0
        return 100.0 * self.avg_gain / moved

    def lower_band(self):
        """Lower Bollinger band over the last 20 typical prices, or None."""
        if len(self.typicals) < BAND_BARS:
            return None
        window = self.typicals[-BAND_BARS:]
        mean = sum(window) / BAND_BARS
        variance = sum((x - mean) * (x - mean) for x in window) / BAND_BARS
        return mean - BAND_SIGMAS * math.sqrt(variance)

    def high20(self):
        """Highest close of the 20 bars before the current one, or None.

        The current bar is left out on purpose: the washout depth is
        measured from the high established before the bounce bar, so a
        bounce bar that itself prints a new high cannot shrink the dip
        being measured.
        """
        if len(self.closes) < HIGH_BARS + 1:
            return None
        return max(self.closes[-HIGH_BARS - 1:-1])


class DipBounceBot:
    """One washout at a time, full size, two round trips at most."""

    def __init__(self):
        self.series = _Series()
        self.round_trips = 0
        self._held = False
        self._bars_seen = 0
        self._cooldown_until = 0

    def _sell_order(self, qty):
        return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]

    def _maybe_exit(self, state, held):
        rsi = self.series.rsi()
        if rsi is not None and rsi > RSI_EXIT_MIN:
            return self._sell_order(held.qty)
        value = state.value(SYMBOL, held.qty)
        cost = held.cost
        if value * 10000 >= cost * (10000 + TAKE_PROFIT_BPS):
            return self._sell_order(held.qty)
        if value * 10000 <= cost * (10000 - STOP_LOSS_BPS):
            return self._sell_order(held.qty)
        return []

    def _entry_signal(self, close):
        rsi = self.series.rsi()
        if rsi is None or rsi >= RSI_ENTRY_MAX:
            return False
        lower = self.series.lower_band()
        if lower is None or close >= lower:
            return False
        high = self.series.high20()
        if high is None:
            return False
        # Close at least 1.0% below the 20-bar high (integer bps math).
        if close * 10000 > high * (10000 - DIP_MIN_BPS):
            return False
        # Bounce confirmed: one rising close. (Two in a row never
        # fires on the dev window: by then RSI is back above 30.)
        closes = self.series.closes
        if len(closes) < 2:
            return False
        if not (closes[-1] > closes[-2]):
            return False
        return True

    def on_batch(self, state, batch):
        fresh = False
        for bar in batch.get("bars", []):
            if bar.get("symbol") == SYMBOL:
                self.series.push(bar)
                self._bars_seen += 1
                fresh = True
        # A round trip completes when a held position disappears.
        held_now = SYMBOL in state.positions
        if self._held and not held_now:
            self.round_trips += 1
            self._cooldown_until = self._bars_seen + COOLDOWN_BARS
        self._held = held_now
        if state.warming_up:
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        held = state.positions.get(SYMBOL)
        if held is not None:
            return self._maybe_exit(state, held)
        if not fresh:
            return []
        if self.round_trips >= MAX_ROUND_TRIPS:
            return []
        if self._bars_seen <= self._cooldown_until:
            return []
        if self._entry_signal(close):
            cash = state.cash
            if cash <= 0:
                return []
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []


makefun_bars.run(DipBounceBot().on_batch)
