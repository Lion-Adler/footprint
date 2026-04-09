"""
backtest.py
-----------
Движок бэктеста. Без классов — только функции.

Логика сделки:
  Сигнал на закрытии свечи i
    → вход по open  свечи i+1
    → выход по close свечи i+1
  Комиссия: 0.055% на вход + 0.055% на выход = 0.11% на roundtrip.
"""

import numpy as np

COMMISSION_PER_SIDE = 0.00055   # 0.055 %


# ─── один бэктест ────────────────────────────────────────────────────────────

def run_backtest(candles: list, strategy_fn, commission: float = COMMISSION_PER_SIDE) -> dict:
    """
    Запускает одну стратегию на списке footprint-свечей.
    Возвращает словарь с метриками и списком сделок.
    """
    if len(candles) < 3:
        return _empty_result()

    trades    = []
    equity    = [1.0]
    equity_ts = [candles[0]["ts"]]

    for i in range(len(candles) - 1):
        # ── сигнал генерируется на закрытии свечи i ───────────────────────
        try:
            signal = strategy_fn(candles, i)
        except Exception:
            signal = False

        if signal:
            entry = candles[i + 1]["open"]
            exit_ = candles[i + 1]["close"]

            if entry <= 0:
                equity.append(equity[-1])
                equity_ts.append(candles[i + 1]["ts"])
                continue

            raw_pnl = (exit_ - entry) / entry
            net_pnl = raw_pnl - 2.0 * commission    # вход + выход

            trades.append({
                "entry_ts":  candles[i + 1]["ts"],
                "entry":     entry,
                "exit":      exit_,
                "raw_pnl":   raw_pnl,
                "net_pnl":   net_pnl,
            })
            equity.append(equity[-1] * (1.0 + net_pnl))
        else:
            equity.append(equity[-1])

        equity_ts.append(candles[i + 1]["ts"])

    return _calc_stats(trades, equity, equity_ts)


# ─── статистика ──────────────────────────────────────────────────────────────

def _empty_result():
    return {
        "n_trades":      0,
        "win_rate":      0.0,
        "total_return":  0.0,
        "sharpe":        0.0,
        "max_drawdown":  0.0,
        "profit_factor": 0.0,
        "avg_pnl":       0.0,
        "equity":        [1.0],
        "equity_ts":     [],
        "trades":        [],
    }


def _calc_stats(trades: list, equity: list, equity_ts: list) -> dict:
    n = len(trades)
    if n == 0:
        return _empty_result()

    pnls   = np.array([t["net_pnl"] for t in trades], dtype=np.float64)
    wins   = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    win_rate     = len(wins) / n
    total_return = equity[-1] - 1.0
    avg_pnl      = float(pnls.mean())

    # Sharpe (аннуализированный, аппроксимация через сделки → x√252)
    std = float(pnls.std())
    sharpe = (avg_pnl / std) * (252 ** 0.5) if std > 1e-12 else 0.0

    # Max Drawdown
    eq_arr = np.array(equity, dtype=np.float64)
    peak   = np.maximum.accumulate(eq_arr)
    dd     = (eq_arr - peak) / peak
    max_dd = float(dd.min())

    # Profit Factor
    gp = float(wins.sum())   if len(wins)   > 0 else 0.0
    gl = float(abs(losses.sum())) if len(losses) > 0 else 0.0
    pf = gp / gl if gl > 1e-12 else (99.9 if gp > 0 else 0.0)

    return {
        "n_trades":      n,
        "win_rate":      round(win_rate * 100, 1),
        "total_return":  round(total_return * 100, 2),
        "sharpe":        round(sharpe, 3),
        "max_drawdown":  round(max_dd * 100, 2),
        "profit_factor": round(min(pf, 99.9), 2),
        "avg_pnl":       round(avg_pnl * 100, 4),
        "equity":        equity,
        "equity_ts":     equity_ts,
        "trades":        trades,
    }


# ─── запуск всех стратегий на всех таймфреймах ───────────────────────────────

def run_all_backtests(candles_by_tf: dict, strategies: list,
                      commission: float = COMMISSION_PER_SIDE) -> dict:
    """
    candles_by_tf: {"4h": [...], "6h": [...], "12h": [...], "24h": [...]}
    strategies:    список (name, fn) из ALL_STRATEGIES
    Возвращает: {"4h": {"S01_...": result_dict, ...}, ...}
    """
    results = {}
    total   = len(candles_by_tf) * len(strategies)
    done    = 0

    for tf_name, candles in candles_by_tf.items():
        results[tf_name] = {}
        print(f"\n  Таймфрейм {tf_name}  ({len(candles)} свечей)")
        print("  " + "-" * 65)

        for sname, sfn in strategies:
            res = run_backtest(candles, sfn, commission)
            results[tf_name][sname] = res
            done += 1

            flag = "✓" if res["total_return"] > 0 else "✗"
            print(f"  {flag} [{done:>3}/{total}] {sname:<30} "
                  f"n={res['n_trades']:>5}  "
                  f"ret={res['total_return']:>+7.2f}%  "
                  f"sh={res['sharpe']:>+6.2f}  "
                  f"dd={res['max_drawdown']:>6.2f}%")

    return results
