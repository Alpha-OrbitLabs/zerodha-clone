"""
1-second scalping template
- Requires: python 3.8+, pip install pandas numpy asyncio websockets python-dotenv
- Replace Broker class methods with your broker/exchange SDK calls.
- Workflow: ingest ticks -> build 1s bars -> compute indicators -> on bar close generate signal -> send order -> risk management
"""

import asyncio
import time
import os
import math
from collections import deque
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import logging

load_dotenv()

# ---------- CONFIG ----------
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")    # replace with your symbol format
TRADE_SIZE_PERCENT = 0.005   # 0.5% of equity per trade
MAX_DAILY_LOSS_PCT = 0.02    # 2% daily stop
RISK_PER_TRADE_PCT = 0.005   # 0.5% risk per trade (used to calc stops)
EMA_FAST = 5                 # very fast EMA on 1s bars
EMA_SLOW = 13
VOLUME_MULTIPLIER = 3.0      # require volume > mean * multiplier
BAR_SECONDS = 1
MIN_EQUITY_TO_TRADE = 100    # currency units
LOGFILE = "algo_1s.log"
# ----------------------------

# Setup logging
logging.basicConfig(filename=LOGFILE,
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

# ---------- Simple Broker placeholder ----------
class Broker:
    """
    Replace these methods with actual broker/exchange API calls.
    Methods should be implemented synchronously or wrapped for async use.
    """
    def __init__(self, api_key=None, api_secret=None):
        self.api_key = 2ocqgjbjp3vnw58v
        self.api_secret = zxfgh18kv9pysurtekz8v17ii5w57e83
        self.cash = 10000.0  # simulated/paper equity
        self.position = 0    # positive for long, negative for short
        self.entry_price = None
        self.day_pnl = 0.0

    def get_equity(self):
        return self.cash + (self.position * (self.entry_price or 0))

    def place_limit_buy(self, symbol, qty, price, stop_loss=None, take_profit=None, tag=None):
        logging.info(f"[BROKER] PLACE BUY qty={qty} price={price} stop={stop_loss} tp={take_profit} tag={tag}")
        # For real broker: send order and return order id / fill info
        self.position += qty
        self.entry_price = price
        return {"status": "filled", "filled_price": price}

    def place_limit_sell(self, symbol, qty, price, stop_loss=None, take_profit=None, tag=None):
        logging.info(f"[BROKER] PLACE SELL qty={qty} price={price} stop={stop_loss} tp={take_profit} tag={tag}")
        self.position -= qty
        self.entry_price = price if self.position != 0 else None
        return {"status": "filled", "filled_price": price}

    def close_all(self, market_price):
        pnl = 0.0
        if self.position != 0:
            pnl = (market_price - self.entry_price) * self.position
            self.cash += pnl
            logging.info(f"[BROKER] Close all pos {self.position} at {market_price} pnl={pnl}")
            self.position = 0
            self.entry_price = None
            self.day_pnl += pnl
        return pnl

    def get_position(self):
        return {"qty": self.position, "entry": self.entry_price}

# ---------- Data aggregator: build 1-second bars ----------
class BarBuilder:
    def __init__(self, bar_seconds=1):
        self.bar_seconds = bar_seconds
        self.current_bar = None  # dict: {ts_open, open, high, low, close, volume}
        self.last_bar_ts = None

    def ingest_tick(self, tick_time_ts, price, volume):
        # tick_time_ts: epoch seconds (float)
        bar_ts = int(tick_time_ts // self.bar_seconds) * self.bar_seconds
        if self.current_bar is None or bar_ts != self.last_bar_ts:
            # flush old bar
            bar = self.current_bar
            self.current_bar = {"ts_open": bar_ts, "open": price, "high": price, "low": price, "close": price, "volume": volume}
            self.last_bar_ts = bar_ts
            return bar  # previous bar returned (may be None)
        else:
            b = self.current_bar
            b["high"] = max(b["high"], price)
            b["low"] = min(b["low"], price)
            b["close"] = price
            b["volume"] += volume
            return None

# ---------- Indicator helpers ----------
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ---------- Strategy core ----------
class OneSecStrategy:
    def __init__(self, broker: Broker):
        self.broker = broker
        # keep a deque for recent bars
        self.bars = deque(maxlen=1000)  # store as dicts
        self.df = pd.DataFrame()
        self.enabled = True
        self.last_signal = None

    def on_bar(self, bar):
        # bar: dict with ts_open, open, high, low, close, volume
        if bar is None:
            return
        self.bars.append(bar)
        self.df = pd.DataFrame(list(self.bars))
        self.df['dt'] = pd.to_datetime(self.df['ts_open'], unit='s')
        # compute indicators when we have sufficient bars
        if len(self.df) < EMA_SLOW + 5:
            return
        self.df['ema_fast'] = ema(self.df['close'], EMA_FAST)
        self.df['ema_slow'] = ema(self.df['close'], EMA_SLOW)
        self.df['vol_ma'] = self.df['volume'].rolling(window=30, min_periods=5).mean().fillna(0)
        latest = self.df.iloc[-1]
        prev = self.df.iloc[-2]

        # signal rules
        crossover_up = (prev['ema_fast'] <= prev['ema_slow']) and (latest['ema_fast'] > latest['ema_slow'])
        crossover_dn = (prev['ema_fast'] >= prev['ema_slow']) and (latest['ema_fast'] < latest['ema_slow'])

        vol_spike = latest['volume'] > (latest['vol_ma'] * VOLUME_MULTIPLIER)
        momentum = (latest['close'] - prev['close']) / prev['close']

        # Only take trades when both crossover and volume spike AND small momentum filter
        if crossover_up and vol_spike and momentum > 0:
            self.try_enter_long(latest)
        elif crossover_dn and vol_spike and momentum < 0:
            self.try_enter_short(latest)
        # optional: add exit on reverse crossover or take-profit/stop-loss managed by broker OCO

    def calc_qty(self, price):
        equity = self.broker.get_equity()
        # size by percentage of equity
        usd_to_risk = equity * TRADE_SIZE_PERCENT
        qty = math.floor(usd_to_risk / price)
        return max(qty, 0)

    def try_enter_long(self, latest):
        if not self.enabled:
            return
        pos = self.broker.get_position()
        if pos['qty'] > 0:
            return  # already long
        price = latest['close']
        qty = self.calc_qty(price)
        if qty <= 0 or self.broker.get_equity() < MIN_EQUITY_TO_TRADE:
            logging.info("Insufficient qty/equity to enter")
            return
        # set stop based on ATR-like small fixed stop or percent
        stop_price = price * (1 - RISK_PER_TRADE_PCT)
        tp_price = price * (1 + (RISK_PER_TRADE_PCT * 1.8))
        result = self.broker.place_limit_buy(SYMBOL, qty, price, stop_loss=stop_price, take_profit=tp_price, tag="entry_long_1s")
        logging.info(f"Entered LONG qty={qty} price={price} stop={stop_price} tp={tp_price} res={result}")
        self.last_signal = ("LONG", price)

    def try_enter_short(self, latest):
        if not self.enabled:
            return
        pos = self.broker.get_position()
        if pos['qty'] < 0:
            return  # already short
        price = latest['close']
        qty = self.calc_qty(price)
        if qty <= 0 or self.broker.get_equity() < MIN_EQUITY_TO_TRADE:
            logging.info("Insufficient qty/equity to enter short")
            return
        stop_price = price * (1 + RISK_PER_TRADE_PCT)
        tp_price = price * (1 - (RISK_PER_TRADE_PCT * 1.8))
        result = self.broker.place_limit_sell(SYMBOL, qty, price, stop_loss=stop_price, take_profit=tp_price, tag="entry_short_1s")
        logging.info(f"Entered SHORT qty={qty} price={price} stop={stop_price} tp={tp_price} res={result}")
        self.last_signal = ("SHORT", price)

    def risk_check(self):
        # daily loss check; if triggered, disable trading for the day
        if abs(self.broker.day_pnl) >= MAX_DAILY_LOSS_PCT * (self.broker.cash + 0):
            logging.warning("Daily loss threshold reached. Disabling trading.")
            self.enabled = False
            # optionally close positions
            # market_price = self.df.iloc[-1]['close']
            # self.broker.close_all(market_price)

# ---------- Runner: simulate ticks or connect to websocket ----------
async def fake_tick_stream(strategy: OneSecStrategy, duration_seconds=30):
    """
    For testing: generate synthetic ticks with small random walk.
    """
    import random
    bb = BarBuilder(bar_seconds=BAR_SECONDS)
    price = 50000.0
    t0 = int(time.time())
    for i in range(duration_seconds * 5):  # 5 ticks per second
        # simulate tick
        tick_time = time.time()
        price += random.uniform(-0.5, 0.5)
        vol = random.uniform(0.01, 0.3)
        finished_bar = bb.ingest_tick(tick_time, price, vol)
        if finished_bar:
            strategy.on_bar(finished_bar)
            strategy.risk_check()
        await asyncio.sleep(0.2)  # simulate 5 ticks/second

async def main_live_loop():
    broker = Broker(api_key=os.getenv("API_KEY"), api_secret=os.getenv("API_SECRET"))
    strat = OneSecStrategy(broker)

    # Replace this part with your exchange websocket integration that yields (ts, price, volume)
    # Example: connect to Binance websocket or broker's tick socket and call bb.ingest_tick
    await fake_tick_stream(strat, duration_seconds=120)  # run for 2 minutes fake

if __name__ == "__main__":
    try:
        asyncio.run(main_live_loop())
    except KeyboardInterrupt:
        logging.info("Stopped by user")
