"""
footprint.py
------------
Строим footprint-свечи из тиковых данных.
Весь математический core — через Numba @njit для максимальной скорости.
Работаем без классов — только функции.
"""

import gc
import math
import numpy as np
from numba import njit

# ─── константы ───────────────────────────────────────────────────────────────

TICK_SIZE         = 1.0    # $1 на уровень для BTC
VALUE_AREA_PCT    = 0.70   # 70% объёма = value area
IMBALANCE_THR     = 3.0    # порог дисбаланса ask/bid (3:1)
MIN_IMBALANCE_VOL = 0.005  # минимальный объём уровня для учёта дисбаланса
MIN_TRADES        = 5      # меньше 5 сделок — свечу пропускаем


# ════════════════════════════════════════════════════════════════════════════
#  NUMBA-ЯДРО
# ════════════════════════════════════════════════════════════════════════════

@njit(cache=True)
def _build_fp_core(prices, sizes, is_buy_arr, tick_size):
    """
    Собирает footprint-массивы из тиков одной свечи.
    Возвращает: (levels, ask_vols, bid_vols)
      levels   — цены уровней (от min к max с шагом tick_size)
      ask_vols — объём покупок (buyer-taker) на каждом уровне
      bid_vols — объём продаж (seller-taker) на каждом уровне
    """
    n = len(prices)
    if n == 0:
        empty = np.zeros(1, dtype=np.float64)
        return empty, empty, empty

    # ── квантование и поиск диапазона ────────────────────────────────────────
    p_min = math.floor(prices[0] / tick_size + 0.5) * tick_size
    p_max = p_min
    for i in range(n):
        qp = math.floor(prices[i] / tick_size + 0.5) * tick_size
        if qp < p_min:
            p_min = qp
        if qp > p_max:
            p_max = qp

    n_levels = int(round((p_max - p_min) / tick_size)) + 1
    if n_levels > 100_000:          # страховка от аномалий
        n_levels = 100_000

    levels   = np.empty(n_levels, dtype=np.float64)
    ask_vols = np.zeros(n_levels, dtype=np.float64)
    bid_vols = np.zeros(n_levels, dtype=np.float64)

    for i in range(n_levels):
        levels[i] = p_min + i * tick_size

    # ── распределяем объём по уровням ────────────────────────────────────────
    for i in range(n):
        qp  = math.floor(prices[i] / tick_size + 0.5) * tick_size
        idx = int(round((qp - p_min) / tick_size))
        if 0 <= idx < n_levels:
            if is_buy_arr[i]:
                ask_vols[idx] += sizes[i]
            else:
                bid_vols[idx] += sizes[i]

    return levels, ask_vols, bid_vols


@njit(cache=True)
def _calc_poc_val_vah(levels, ask_vols, bid_vols, value_area_pct):
    """
    Вычисляет POC, VAL, VAH методом пошагового расширения от POC.
    Возвращает (poc_price, val_price, vah_price).
    """
    n = len(levels)
    if n == 0:
        return 0.0, 0.0, 0.0

    total_vols = ask_vols + bid_vols
    total_vol  = 0.0
    for i in range(n):
        total_vol += total_vols[i]

    if total_vol <= 0.0:
        mid = n // 2
        return levels[mid], levels[0], levels[n - 1]

    # ── POC ──────────────────────────────────────────────────────────────────
    poc_idx  = 0
    max_vol  = -1.0
    for i in range(n):
        if total_vols[i] > max_vol:
            max_vol  = total_vols[i]
            poc_idx  = i

    # ── Value Area ────────────────────────────────────────────────────────────
    target = total_vol * value_area_pct
    acc    = total_vols[poc_idx]
    lo     = poc_idx
    hi     = poc_idx

    while acc < target:
        can_up = hi + 1 < n
        can_dn = lo - 1 >= 0
        if not can_up and not can_dn:
            break
        v_up = total_vols[hi + 1] if can_up else -1.0
        v_dn = total_vols[lo - 1] if can_dn else -1.0
        if v_up >= v_dn:
            hi  += 1
            acc += total_vols[hi]
        else:
            lo  -= 1
            acc += total_vols[lo]

    return levels[poc_idx], levels[lo], levels[hi]


@njit(cache=True)
def _calc_imbalances(ask_vols, bid_vols, threshold, min_vol):
    """
    Диагональные дисбалансы (стандарт footprint):
      imb_ask[i] = True  →  ask[i] >> bid[i-1]  (давление покупателей)
      imb_bid[i] = True  →  bid[i] >> ask[i-1]  (давление продавцов)
    Возвращает (imb_ask, imb_bid) — массивы bool.
    """
    n       = len(ask_vols)
    imb_ask = np.zeros(n, dtype=np.bool_)
    imb_bid = np.zeros(n, dtype=np.bool_)

    for i in range(1, n):
        a  = ask_vols[i]
        b0 = bid_vols[i - 1]
        b  = bid_vols[i]
        a0 = ask_vols[i - 1]

        if a >= min_vol:
            ratio = a / (b0 + 1e-10)
            if ratio >= threshold:
                imb_ask[i] = True

        if b >= min_vol:
            ratio = b / (a0 + 1e-10)
            if ratio >= threshold:
                imb_bid[i] = True

    return imb_ask, imb_bid


@njit(cache=True)
def _max_streak(bool_arr):
    """Максимальная серия подряд идущих True."""
    best = 0
    cur  = 0
    for i in range(len(bool_arr)):
        if bool_arr[i]:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


@njit(cache=True)
def _zone_deltas(ask_vols, bid_vols):
    """
    Дельта в нижней / средней / верхней трети свечи.
    Возвращает (d_low, d_mid, d_high).
    """
    n  = len(ask_vols)
    z0 = n // 3
    z1 = 2 * (n // 3)

    d_low = d_mid = d_hi = 0.0
    for i in range(n):
        d = ask_vols[i] - bid_vols[i]
        if i < z0:
            d_low += d
        elif i < z1:
            d_mid += d
        else:
            d_hi  += d

    return d_low, d_mid, d_hi


@njit(cache=True)
def _ohlcv(prices, sizes, is_buy_arr):
    """OHLCV + buy_vol + sell_vol из массивов тиков."""
    n = len(prices)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    o = prices[0]
    c = prices[n - 1]
    h = prices[0]
    l = prices[0]
    vol = bvol = svol = 0.0

    for i in range(n):
        if prices[i] > h:
            h = prices[i]
        if prices[i] < l:
            l = prices[i]
        vol += sizes[i]
        if is_buy_arr[i]:
            bvol += sizes[i]
        else:
            svol += sizes[i]

    return o, h, l, c, vol, bvol, svol


# ════════════════════════════════════════════════════════════════════════════
#  PYTHON-ОБЁРТКИ
# ════════════════════════════════════════════════════════════════════════════

def build_one_candle(ts_start: int, ts_end: int,
                     timestamps, prices, sizes, is_buy) -> dict | None:
    """
    Строит один footprint-словарь для временного окна [ts_start, ts_end).
    Возвращает None если данных нет или их слишком мало.
    """
    mask = (timestamps >= ts_start) & (timestamps < ts_end)
    if mask.sum() < MIN_TRADES:
        return None

    p  = prices[mask]
    s  = sizes[mask]
    b  = is_buy[mask]

    # ── базовые OHLCV ────────────────────────────────────────────────────────
    o, h, l, c, vol, buy_vol, sell_vol = _ohlcv(p, s, b)
    delta = buy_vol - sell_vol

    # ── footprint ────────────────────────────────────────────────────────────
    levels, ask_vols, bid_vols = _build_fp_core(p, s, b, TICK_SIZE)

    # ── POC / VAL / VAH ──────────────────────────────────────────────────────
    poc, val, vah = _calc_poc_val_vah(levels, ask_vols, bid_vols, VALUE_AREA_PCT)

    # ── дисбалансы ───────────────────────────────────────────────────────────
    imb_ask, imb_bid = _calc_imbalances(ask_vols, bid_vols,
                                        IMBALANCE_THR, MIN_IMBALANCE_VOL)
    stacked_ask = _max_streak(imb_ask)
    stacked_bid = _max_streak(imb_bid)

    # ── зональные дельты ─────────────────────────────────────────────────────
    d_low, d_mid, d_hi = _zone_deltas(ask_vols, bid_vols)

    # ── относительное положение уровней ──────────────────────────────────────
    rng = h - l if (h - l) > 0 else 1e-9
    poc_pct = (poc - l) / rng
    vah_pct = (vah - l) / rng
    val_pct = (val - l) / rng

    return {
        "ts":          ts_start,
        "open":        o,
        "high":        h,
        "low":         l,
        "close":       c,
        "volume":      vol,
        "buy_vol":     buy_vol,
        "sell_vol":    sell_vol,
        "delta":       delta,
        "cum_delta":   0.0,   # заполняется позже в main
        "levels":      levels,
        "ask_vols":    ask_vols,
        "bid_vols":    bid_vols,
        "poc":         poc,
        "vah":         vah,
        "val":         val,
        "n_ask_imb":   int(imb_ask.sum()),
        "n_bid_imb":   int(imb_bid.sum()),
        "stacked_ask": stacked_ask,
        "stacked_bid": stacked_bid,
        "delta_low":   d_low,
        "delta_mid":   d_mid,
        "delta_high":  d_hi,
        "poc_pct":     poc_pct,
        "vah_pct":     vah_pct,
        "val_pct":     val_pct,
    }


def build_candles_for_day(day_ts_ms: int, tf_seconds: int,
                          timestamps, prices, sizes, is_buy) -> list:
    """
    Строит все footprint-свечи для одного UTC-дня при заданном таймфрейме.
    day_ts_ms — начало дня в миллисекундах (UTC midnight).
    tf_seconds — длина свечи в секундах (14400, 21600, 43200, 86400).
    """
    candles    = []
    tf_ms      = tf_seconds * 1000
    day_end_ms = day_ts_ms + 86_400_000

    t = day_ts_ms
    while t < day_end_ms:
        c = build_one_candle(t, t + tf_ms, timestamps, prices, sizes, is_buy)
        if c is not None:
            candles.append(c)
        t += tf_ms

    return candles


def fill_cumulative_delta(candles: list) -> None:
    """Проставляет накопительную дельту по всему списку свечей (in-place)."""
    cum = 0.0
    for c in candles:
        cum += c["delta"]
        c["cum_delta"] = cum
