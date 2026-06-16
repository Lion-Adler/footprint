# Footprint Backtest — 30 Strategies × 4 Timeframes

## Project File Structure

```
backtest_strategy_ob_t6/
├── main.py              ← entry point
├── data_loader.py       ← Binance + Bybit data loading (day by day)
├── footprint.py         ← footprint construction (Numba kernel)
├── strategies.py        ← 30 trading strategies
├── backtest.py          ← backtest engine and metrics
├── requirements.txt
└── results/             ← created automatically
    ├── backtest_results.csv
    ├── equity_4h.png
    ├── equity_6h.png
    ├── equity_12h.png
    └── equity_24h.png
```

Data is read from:

```
../backtest_strategy_ob_t1/data/binance-f/   ← monthly files (BTCUSDT-agg-YYYY-MM.parquet)
../backtest_strategy_ob_t1/data/bybit-f/     ← daily files  (BTCUSDTyyyy-mm-dd.parquet)
```

---

## Installation

```bash
cd ~/worksoft/backtest_strategy_ob_t6
pip install -r requirements.txt
```

---

## Running

```bash
python main.py
```

The first run takes longer — Numba compiles JIT functions (~30 s).  
Subsequent runs are faster thanks to the `__pycache__` compilation cache.

---

## Backtest Logic

| Step       | What Happens                                     |
|------------|--------------------------------------------------|
| Signal     | Computed on the **close** of candle `i`          |
| Entry      | Executed at the **open** of candle `i+1`         |
| Exit       | Executed at the **close** of candle `i+1`        |
| Commission | **0.055%** entry + **0.055%** exit = **0.11% roundtrip** |

Long-only. Each signal produces one trade (no position accumulation).

---

## Timeframes

| TF  | Candles per Day |
|-----|-----------------|
| 4h  | 6               |
| 6h  | 4               |
| 12h | 2               |
| 24h | 1               |

---

## 30 Strategies — Overview

### Group 1 — Delta

| #   | Name                  | Idea                                          |
|-----|-----------------------|-----------------------------------------------|
| S01 | strong_delta          | delta/volume > 20%                            |
| S02 | delta_accel           | delta is accelerating (+30%)                  |
| S03 | price_delta_momentum  | price ↑ + delta ↑                             |
| S04 | delta_trend_3         | 3 consecutive candles with growing delta      |
| S05 | delta_turnover        | delta reversal from − to +                    |
| S06 | delta_ratio_spike     | delta/volume spike vs rolling average         |
| S07 | cum_delta_rising      | cumulative delta rising for 3 candles         |
| S08 | multibar_delta_sum    | sum of 3 deltas > 0, last ≥ previous          |
| S09 | two_pos_delta         | 2 consecutive candles with delta > 0          |
| S10 | buy_vol_dominance     | buy_vol > 60% of total volume                 |

### Group 2 — Imbalances

| #   | Name                  | Idea                                          |
|-----|-----------------------|-----------------------------------------------|
| S11 | stacked_ask_3         | 3+ consecutive ask-imbalances                 |
| S12 | stacked_ask_2_delta   | 2+ imbalances + delta > 0                     |
| S13 | ask_imb_vol_surge     | imbalances + volume > 1.4×                    |
| S14 | ask_imb_at_lows       | imbalances in the lower zone of the candle    |
| S15 | bid_exhaust_response  | many bid-imbalances, but delta > 0            |

### Group 3 — POC / Value Area

| #   | Name                  | Idea                                          |
|-----|-----------------------|-----------------------------------------------|
| S16 | poc_breakout          | close > POC[-1] + delta                       |
| S17 | vah_breakout          | close > VAH[-1] + delta                       |
| S18 | val_rejection         | VAL test + bullish bounce                     |
| S19 | poc_at_high           | POC in the upper part of the candle           |
| S20 | poc_migration_up      | POC rising for 3 consecutive candles          |
| S21 | poc_breakout_stacked  | POC breakout + stacked_ask ≥ 2                |
| S22 | close_above_vah       | close ≥ own VAH                               |
| S23 | near_val_with_delta   | close near VAL + delta > 0                   |

### Group 4 — Volume / Candlestick Patterns

| #   | Name                  | Idea                                          |
|-----|-----------------------|-----------------------------------------------|
| S24 | volume_surge_bull     | volume > 1.8× average + delta                 |
| S25 | seller_exhaustion     | sell_vol spike, but bullish close             |
| S26 | strong_close          | (close−low)/range > 80% + delta               |
| S27 | bullish_reversal      | red → green candle + delta                    |
| S28 | inside_bar_coil       | inside bar + stacked_ask ≥ 2                  |
| S29 | range_expansion       | range expansion > 1.5× + close at top        |
| S30 | composite             | 5+ out of 8 bullish criteria                  |

---

## Output Metrics (CSV)

| Column           | Description                          |
|------------------|--------------------------------------|
| n_trades         | Total number of trades               |
| win_rate_%       | Percentage of winning trades         |
| total_return_%   | Total return over the period         |
| sharpe           | Annualized Sharpe ratio              |
| max_drawdown_%   | Maximum drawdown                     |
| profit_factor    | Gross profit / Gross loss            |
| avg_pnl_%        | Average P&L per trade                |

---

## Frequently Asked Questions

**Why Numba?**  
Processing 50+ million ticks requires fast math. Numba compiles Python loops into machine code — delivering a **50–200× speedup** compared to pure Python.

**Why is data loaded day by day?**  
The combined Bybit + Binance dataset is ~30 GB. Loading everything at once is not feasible. The engine reads one day, builds candles, frees the tick data, and moves to the next day.

**How do I add a custom strategy?**  
In `strategies.py`, add a function:

```python
def s31_my_strategy(candles, i):
    ...
```

Then register it in the strategy list:

```python
("S31_my_strategy", s31_my_strategy)
```

That's it — the backtest engine picks it up automatically.
