"""
main.py
-------
Главный оркестратор:
  1. Читает данные день за днём (Binance monthly + Bybit daily)
  2. Строит footprint-свечи для 4h / 6h / 12h / 24h
  3. Запускает 30 стратегий на каждом таймфрейме
  4. Сохраняет CSV + графики equity-кривых

Запуск:  python main.py
"""

import gc
import time
import csv
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from data_loader  import get_all_bybit_dates, load_day_combined
from footprint    import build_candles_for_day, fill_cumulative_delta
from strategies   import ALL_STRATEGIES
from backtest     import run_all_backtests, COMMISSION_PER_SIDE

# ─── настройки ───────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("results")

TIMEFRAMES = {
    "4h":  4  * 3_600,
    "6h":  6  * 3_600,
    "12h": 12 * 3_600,
    "24h": 24 * 3_600,
}

COMMISSION = COMMISSION_PER_SIDE   # 0.055 %

TOP_N_PLOT = 6    # сколько лучших кривых показывать на графике


# ════════════════════════════════════════════════════════════════════════════
#  ШАГ 1: НАКОПЛЕНИЕ FOOTPRINT-СВЕЧЕЙ
# ════════════════════════════════════════════════════════════════════════════

def collect_all_candles() -> dict:
    """
    Проходим по всем дням, читаем тики, строим footprint-свечи,
    немедленно освобождаем тиковые данные из памяти.
    """
    dates_files = get_all_bybit_dates()
    if not dates_files:
        print("Ошибка: не найдено ни одного файла Bybit в ../backtest_strategy_ob_t1/data/bybit-f/")
        raise SystemExit(1)

    print(f"Найдено дней с данными: {len(dates_files)}")
    print(f"Период: {dates_files[0][0].date()}  →  {dates_files[-1][0].date()}")

    candles_by_tf = {tf: [] for tf in TIMEFRAMES}
    total = len(dates_files)

    for idx, (date, bybit_file) in enumerate(dates_files):
        t0 = time.perf_counter()
        date_str = date.strftime("%Y-%m-%d")
        print(f"[{idx + 1:>4}/{total}] {date_str} ... ", end="", flush=True)

        # ── загружаем и объединяем тики ──────────────────────────────────────
        result = load_day_combined(date, bybit_file)
        if result is None:
            print("нет данных, пропуск")
            continue

        timestamps, prices, sizes, is_buy = result
        day_ts_ms = int(date.timestamp()) * 1000

        # ── строим свечи для каждого таймфрейма ──────────────────────────────
        for tf_name, tf_secs in TIMEFRAMES.items():
            day_candles = build_candles_for_day(
                day_ts_ms, tf_secs, timestamps, prices, sizes, is_buy
            )
            candles_by_tf[tf_name].extend(day_candles)

        # ── освобождаем тиковые данные немедленно ────────────────────────────
        del timestamps, prices, sizes, is_buy, result
        gc.collect()

        elapsed = time.perf_counter() - t0
        counts  = "  ".join(
            f"{tf}:{len(candles_by_tf[tf]):>5}"
            for tf in TIMEFRAMES
        )
        print(f"готово ({elapsed:.1f}s)   свечей всего: {counts}")

    # ── накопительная дельта (нужна стратегии S07) ───────────────────────────
    for tf in TIMEFRAMES:
        fill_cumulative_delta(candles_by_tf[tf])

    print("\nИтог по свечам:")
    for tf, candles in candles_by_tf.items():
        print(f"  {tf:>4}: {len(candles):>6} свечей")

    return candles_by_tf


# ════════════════════════════════════════════════════════════════════════════
#  ШАГ 2: ОТЧЁТ
# ════════════════════════════════════════════════════════════════════════════

def save_csv(results: dict) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    csv_path = OUTPUT_DIR / "backtest_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "timeframe", "strategy",
            "n_trades", "win_rate_%", "total_return_%",
            "sharpe", "max_drawdown_%", "profit_factor", "avg_pnl_%",
        ])
        for tf, strats in results.items():
            for sname, res in strats.items():
                w.writerow([
                    tf, sname,
                    res["n_trades"],
                    res["win_rate"],
                    res["total_return"],
                    res["sharpe"],
                    res["max_drawdown"],
                    res["profit_factor"],
                    res["avg_pnl"],
                ])
    print(f"\nCSV сохранён: {csv_path}")


def plot_equity_curves(results: dict) -> None:
    """Рисует equity-кривые для топ-N стратегий по каждому таймфрейму."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    for tf, tf_results in results.items():
        # отбираем только стратегии с достаточным кол-вом сделок
        ranked = sorted(
            [(n, r) for n, r in tf_results.items() if r["n_trades"] >= 10],
            key=lambda x: x[1]["sharpe"],
            reverse=True,
        )[:TOP_N_PLOT]

        if not ranked:
            continue

        fig, ax = plt.subplots(figsize=(15, 7))

        for sname, res in ranked:
            eq = res["equity"]
            ts = res["equity_ts"]
            if not ts:
                continue
            dates = [datetime.fromtimestamp(t / 1000, tz=timezone.utc) for t in ts]
            lbl   = (f"{sname}  "
                     f"ret={res['total_return']:+.1f}%  "
                     f"sh={res['sharpe']:.2f}  "
                     f"dd={res['max_drawdown']:.1f}%  "
                     f"n={res['n_trades']}")
            ax.plot(dates, eq, linewidth=1.4, label=lbl)

        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_title(
            f"Топ-{TOP_N_PLOT} стратегий | Таймфрейм {tf} | "
            f"Комиссия {COMMISSION * 100:.3f}% / сторона",
            fontsize=11,
        )
        ax.set_xlabel("Дата")
        ax.set_ylabel("Стоимость портфеля (старт = 1.0)")
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(True, alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()
        plt.tight_layout()

        out = OUTPUT_DIR / f"equity_{tf}.png"
        plt.savefig(out, dpi=130)
        plt.close(fig)
        print(f"График сохранён: {out}")


def print_summary(results: dict) -> None:
    """Красивая таблица с топ-результатами."""
    W = 95
    print("\n" + "═" * W)
    print(f"{'TF':>5}  {'Стратегия':<32} {'Сделки':>7} {'WR%':>6} "
          f"{'Доход%':>8} {'Sharpe':>7} {'MaxDD%':>7} {'PF':>6}")
    print("═" * W)

    rows = []
    for tf, strats in results.items():
        for sname, res in strats.items():
            if res["n_trades"] > 0:
                rows.append((tf, sname, res))

    rows.sort(key=lambda x: x[2]["sharpe"], reverse=True)

    for tf, sname, res in rows[:50]:
        sign = "+" if res["total_return"] >= 0 else ""
        print(f"{tf:>5}  {sname:<32} {res['n_trades']:>7} "
              f"{res['win_rate']:>5.1f}% "
              f"{sign}{res['total_return']:>7.2f}% "
              f"{res['sharpe']:>+7.3f} "
              f"{res['max_drawdown']:>6.2f}% "
              f"{res['profit_factor']:>6.2f}")

    print("═" * W)

    # ── лучшая стратегия на каждый TF ────────────────────────────────────────
    print("\n  ЛУЧШАЯ СТРАТЕГИЯ ПО КАЖДОМУ ТАЙМФРЕЙМУ (по Sharpe, min 10 сделок):")
    for tf in TIMEFRAMES:
        candidates = [
            (n, r) for n, r in results[tf].items()
            if r["n_trades"] >= 10
        ]
        if not candidates:
            print(f"  {tf:>4}: — нет достаточного числа сделок")
            continue
        best_n, best_r = max(candidates, key=lambda x: x[1]["sharpe"])
        print(f"  {tf:>4}: {best_n:<32} "
              f"ret={best_r['total_return']:+.2f}%  "
              f"sh={best_r['sharpe']:.3f}  "
              f"wr={best_r['win_rate']:.1f}%  "
              f"n={best_r['n_trades']}")
    print()


# ════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  FOOTPRINT BACKTEST  |  30 стратегий × 4 таймфрейма")
    print(f"  Комиссия: {COMMISSION * 100:.3f}% на сторону ({COMMISSION * 200:.3f}% roundtrip)")
    print("=" * 65 + "\n")

    # ── 1. Накапливаем свечи ──────────────────────────────────────────────────
    print("─── Фаза 1: построение footprint-свечей ─────────────────────────")
    candles_by_tf = collect_all_candles()

    # ── 2. Бэктест ───────────────────────────────────────────────────────────
    print("\n─── Фаза 2: бэктест ─────────────────────────────────────────────")
    results = run_all_backtests(candles_by_tf, ALL_STRATEGIES, COMMISSION)

    # ── 3. Отчёт ─────────────────────────────────────────────────────────────
    print("\n─── Фаза 3: отчёт ───────────────────────────────────────────────")
    save_csv(results)
    plot_equity_curves(results)
    print_summary(results)

    print(f"Все файлы в папке: {OUTPUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
