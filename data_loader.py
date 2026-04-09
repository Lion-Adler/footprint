"""
data_loader.py
--------------
Загружает данные Binance и Bybit по одному дню за раз,
чтобы не перегружать оперативную память.
"""

import gc
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import polars as pl

# ─── пути к данным ──────────────────────────────────────────────────────────

BINANCE_DIR = Path("../backtest_strategy_ob_t1/data/binance-f")
BYBIT_DIR   = Path("../backtest_strategy_ob_t1/data/bybit-f")


# ─── обнаружение файлов ──────────────────────────────────────────────────────

def get_all_bybit_dates():
    """
    Возвращает отсортированный список (datetime_utc, Path) по всем
    дневным файлам Bybit (BTCUSDT2025-01-01.parquet …).
    """
    dates = []
    for f in sorted(BYBIT_DIR.glob("BTCUSDT*.parquet")):
        stem = f.stem  # e.g. BTCUSDT2025-01-01
        date_str = stem[7:]  # 2025-01-01
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            dates.append((dt, f))
        except ValueError:
            pass
    return dates


def get_binance_file_for_month(year: int, month: int) -> Path | None:
    fname = f"BTCUSDT-agg-{year}-{month:02d}.parquet"
    p = BINANCE_DIR / fname
    return p if p.exists() else None


# ─── загрузка Binance (ленивая фильтрация — не читаем весь месяц) ────────────

def load_binance_for_day(date: datetime) -> pl.DataFrame | None:
    """
    Загружает агрег-сделки Binance за один UTC-день, используя
    scan_parquet (pushdown-фильтрация по row-group'ам).
    Нормализует: timestamp(ms), price, size, is_buy.
    """
    fpath = get_binance_file_for_month(date.year, date.month)
    if fpath is None:
        return None

    start_ms = int(date.timestamp()) * 1000
    end_ms   = start_ms + 86_400_000          # +24 h в миллисекундах

    try:
        df = (
            pl.scan_parquet(fpath)
            .filter(
                (pl.col("transact_time") >= start_ms) &
                (pl.col("transact_time") <  end_ms)
            )
            .select(["transact_time", "price", "quantity", "is_buyer_maker"])
            .collect()
        )
    except Exception as e:
        print(f"    [Binance] ошибка при чтении {fpath.name}: {e}")
        return None

    if df.is_empty():
        return None

    # is_buyer_maker=True  → продавец-тейкер → sell
    # is_buyer_maker=False → покупатель-тейкер → buy
    df = df.rename({"transact_time": "timestamp", "quantity": "size"}).with_columns(
        (~pl.col("is_buyer_maker")).alias("is_buy")
    ).select(["timestamp", "price", "size", "is_buy"])

    return df


# ─── загрузка Bybit (дневной файл целиком) ───────────────────────────────────

def load_bybit_for_day(file_path: Path) -> pl.DataFrame | None:
    """
    Загружает дневной файл Bybit, нормализует в тот же формат:
    timestamp(ms int64), price(f64), size(f64), is_buy(bool).
    """
    try:
        df = pl.read_parquet(file_path)
    except Exception as e:
        print(f"    [Bybit] ошибка при чтении {file_path.name}: {e}")
        return None

    if df.is_empty():
        return None

    cols = df.columns

    # ── получаем цену ────────────────────────────────────────────────────────
    if "price" in cols:
        pass
    elif "foreignNotional" in cols and "homeNotional" in cols:
        df = df.with_columns(
            (pl.col("foreignNotional") / pl.col("homeNotional")).alias("price")
        )
    elif "grossValue" in cols and "size" in cols:
        # grossValue в сатоши → делим на 1e8 и на size(BTC) → USD
        df = df.with_columns(
            (pl.col("grossValue") / 1e8 / pl.col("size")).alias("price")
        )
    else:
        print(f"    [Bybit] не удалось определить цену в {file_path.name}")
        return None

    # ── timestamp: секунды f64 → миллисекунды int64 ──────────────────────────
    df = df.with_columns(
        (pl.col("timestamp") * 1000).cast(pl.Int64).alias("timestamp"),
        pl.col("price").cast(pl.Float64),
        pl.col("size").cast(pl.Float64),
        (pl.col("side") == "Buy").alias("is_buy"),
    ).select(["timestamp", "price", "size", "is_buy"])

    # Фильтруем мусор
    df = df.filter(pl.col("price") > 0).filter(pl.col("size") > 0)
    return df if not df.is_empty() else None


# ─── объединение источников ──────────────────────────────────────────────────

def load_day_combined(date: datetime, bybit_file: Path):
    """
    Возвращает объединённые (Binance + Bybit) данные за день в виде
    четырёх numpy-массивов: (timestamps, prices, sizes, is_buy).
    Возвращает None, если данных нет.
    После использования — вызвать gc.collect() самостоятельно.
    """
    df_b = load_binance_for_day(date)
    df_y = load_bybit_for_day(bybit_file)

    frames = [f for f in (df_b, df_y) if f is not None]
    if not frames:
        return None

    df = pl.concat(frames).sort("timestamp") if len(frames) == 2 else frames[0].sort("timestamp")

    timestamps = df["timestamp"].to_numpy().astype(np.int64)
    prices     = df["price"].to_numpy().astype(np.float64)
    sizes      = df["size"].to_numpy().astype(np.float64)
    is_buy     = df["is_buy"].to_numpy().astype(np.bool_)

    # Освобождаем polars DataFrame немедленно
    del df, df_b, df_y, frames
    gc.collect()

    return timestamps, prices, sizes, is_buy
