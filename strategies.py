"""
strategies.py
-------------
30 торговых стратегий на основе footprint-данных.
Все стратегии — чистые функции, без классов.

Сигнатура каждой стратегии:
    strategy_fn(candles: list[dict], i: int) -> bool

  candles — список footprint-свечей (уже построенных).
  i       — индекс ТЕКУЩЕЙ (сигнальной) свечи.

Сигнал True означает: войти в лонг на открытии свечи i+1,
выйти на закрытии свечи i+1.
"""

# ─── вспомогательные функции ─────────────────────────────────────────────────

def _avg(candles, i, n, key):
    """Среднее значение поля key по последним n свечам до i (включительно)."""
    start = max(0, i - n + 1)
    vals  = [candles[j][key] for j in range(start, i + 1)]
    return sum(vals) / len(vals) if vals else 0.0


def _avg_range(candles, i, n):
    """Средний диапазон (high-low) за n свечей до i."""
    start = max(0, i - n + 1)
    vals  = [candles[j]["high"] - candles[j]["low"] for j in range(start, i + 1)]
    return sum(vals) / len(vals) if vals else 1e-9


def _avg_ratio(candles, i, n):
    """Средний delta/volume за n свечей."""
    start = max(0, i - n + 1)
    vals  = []
    for j in range(start, i + 1):
        v = candles[j]["volume"]
        if v > 0:
            vals.append(candles[j]["delta"] / v)
    return sum(vals) / len(vals) if vals else 0.0


# ════════════════════════════════════════════════════════════════════════════
#  30 СТРАТЕГИЙ
# ════════════════════════════════════════════════════════════════════════════

# ── ГРУППА 1: Дельта-стратегии ───────────────────────────────────────────────

def s01_strong_buy_delta(candles, i):
    """
    Сильная положительная дельта: buy_vol > 20% от всего объёма сверх нейтрали.
    delta / volume > 0.20.
    """
    c = candles[i]
    if c["volume"] <= 0:
        return False
    return c["delta"] / c["volume"] > 0.20


def s02_delta_acceleration(candles, i):
    """
    Ускорение дельты: текущая дельта выросла на 30%+ по сравнению с предыдущей,
    обе положительные.
    """
    if i < 1:
        return False
    c = candles[i]
    p = candles[i - 1]
    return c["delta"] > 0 and p["delta"] > 0 and c["delta"] > p["delta"] * 1.3


def s03_price_and_delta_momentum(candles, i):
    """
    Цена растёт И дельта растёт одновременно — подтверждение тренда.
    """
    if i < 1:
        return False
    c = candles[i]
    p = candles[i - 1]
    return (c["close"] > p["close"] and
            c["delta"] > p["delta"] and
            c["delta"] > 0)


def s04_delta_trend_3(candles, i):
    """
    Три свечи подряд с растущей положительной дельтой.
    """
    if i < 2:
        return False
    d0 = candles[i - 2]["delta"]
    d1 = candles[i - 1]["delta"]
    d2 = candles[i]["delta"]
    return d0 > 0 and d1 > d0 and d2 > d1


def s05_delta_turnover_bull(candles, i):
    """
    Разворот дельты: предыдущая свеча отрицательная, текущая — сильно
    положительная (перехватили инициативу покупатели).
    """
    if i < 1:
        return False
    c = candles[i]
    p = candles[i - 1]
    return (p["delta"] < 0 and
            c["delta"] > abs(p["delta"]) * 0.5 and
            c["close"] > c["open"])


def s06_delta_ratio_spike(candles, i):
    """
    Текущий delta/volume значительно выше среднего за 5 свечей.
    """
    if i < 5:
        return False
    avg = _avg_ratio(candles, i - 1, 5)
    c   = candles[i]
    cur = c["delta"] / c["volume"] if c["volume"] > 0 else 0.0
    return cur > max(avg * 1.5, 0.15)


def s07_cum_delta_rising(candles, i):
    """
    Накопительная дельта растёт 3 свечи подряд.
    """
    if i < 2:
        return False
    return (candles[i]["cum_delta"] >
            candles[i - 1]["cum_delta"] >
            candles[i - 2]["cum_delta"])


def s08_multibar_delta_sum(candles, i):
    """
    Сумма дельт за 3 свечи положительная, и последняя дельта >= предыдущей.
    """
    if i < 2:
        return False
    d0 = candles[i - 2]["delta"]
    d1 = candles[i - 1]["delta"]
    d2 = candles[i]["delta"]
    return (d0 + d1 + d2) > 0 and d2 > 0 and d2 >= d1


def s09_two_consecutive_positive_delta(candles, i):
    """
    Две свечи подряд с положительной дельтой — устойчивый бычий поток.
    """
    if i < 1:
        return False
    return candles[i]["delta"] > 0 and candles[i - 1]["delta"] > 0


def s10_high_buy_volume_ratio(candles, i):
    """
    Объём покупок > 60% от всего объёма свечи.
    """
    c = candles[i]
    if c["volume"] <= 0:
        return False
    return c["buy_vol"] / c["volume"] > 0.60


# ── ГРУППА 2: Дисбалансы (Imbalances) ────────────────────────────────────────

def s11_stacked_ask_imbalances_3(candles, i):
    """
    Стек из 3+ последовательных ask-дисбалансов — агрессивные покупатели.
    """
    return candles[i]["stacked_ask"] >= 3


def s12_stacked_ask_imbalances_2(candles, i):
    """
    Стек из 2+ ask-дисбалансов + положительная дельта.
    """
    c = candles[i]
    return c["stacked_ask"] >= 2 and c["delta"] > 0


def s13_ask_imbalance_with_volume_surge(candles, i):
    """
    2+ ask-дисбалансов + объём выше среднего по 3 свечам.
    """
    if i < 3:
        return False
    avg_vol = _avg(candles, i - 1, 3, "buy_vol")
    c       = candles[i]
    return c["n_ask_imb"] >= 2 and c["buy_vol"] > avg_vol * 1.4


def s14_ask_imbalance_at_lows(candles, i):
    """
    Дисбалансы в нижней зоне свечи (delta_low > 0) + stacked_ask >= 2.
    Покупатели поглощают продавцов на минимумах.
    """
    c = candles[i]
    return (c["delta_low"] > 0 and
            c["stacked_ask"] >= 2 and
            c["close"] > (c["high"] + c["low"]) / 2)


def s15_bid_exhaustion_with_ask_response(candles, i):
    """
    Много bid-дисбалансов, но дельта всё равно положительная —
    продавцы выдыхаются, покупатели поглощают.
    """
    c = candles[i]
    return (c["n_bid_imb"] >= 2 and
            c["delta"] > 0 and
            c["stacked_ask"] >= 1)


# ── ГРУППА 3: POC и Value Area ────────────────────────────────────────────────

def s16_poc_breakout(candles, i):
    """
    Закрытие выше POC предыдущей свечи + положительная дельта.
    """
    if i < 1:
        return False
    return (candles[i]["close"] > candles[i - 1]["poc"] and
            candles[i]["delta"] > 0)


def s17_vah_breakout(candles, i):
    """
    Закрытие выше VAH предыдущей свечи — выход из зоны ценности вверх.
    """
    if i < 1:
        return False
    return (candles[i]["close"] > candles[i - 1]["vah"] and
            candles[i]["delta"] > 0)


def s18_val_rejection(candles, i):
    """
    Тест VAL предыдущей свечи + отскок (low ≤ val, close > val) + бычья дельта.
    """
    if i < 1:
        return False
    c    = candles[i]
    prev = candles[i - 1]
    return (c["low"]   <= prev["val"] * 1.001 and
            c["close"] >  prev["val"] and
            c["delta"] >  0)


def s19_poc_at_high(candles, i):
    """
    POC находится в верхней части свечи (poc_pct > 0.75) при положительной дельте —
    покупатели доминируют на высоких ценах.
    """
    c = candles[i]
    return c["poc_pct"] > 0.75 and c["delta"] > 0


def s20_poc_migration_up(candles, i):
    """
    POC мигрирует вверх три свечи подряд — бычья ротация.
    """
    if i < 2:
        return False
    return (candles[i]["poc"] >
            candles[i - 1]["poc"] >
            candles[i - 2]["poc"])


def s21_poc_breakout_with_stacked_ask(candles, i):
    """
    Breakout выше POC + stacked_ask >= 2 — подтверждённый пробой.
    """
    if i < 1:
        return False
    c    = candles[i]
    prev = candles[i - 1]
    return (c["close"] > prev["poc"] and
            c["stacked_ask"] >= 2)


def s22_close_above_vah(candles, i):
    """
    Свеча закрывается выше собственного VAH — очень бычья свеча.
    """
    c = candles[i]
    return c["close"] >= c["vah"] and c["delta"] > 0


def s23_price_near_val_with_delta(candles, i):
    """
    Цена закрытия вблизи VAL (< 15% диапазона) при положительной дельте —
    накопление у поддержки.
    """
    c   = candles[i]
    rng = c["high"] - c["low"]
    if rng <= 0:
        return False
    val_dist = abs(c["close"] - c["val"]) / rng
    return val_dist < 0.15 and c["delta"] > 0


# ── ГРУППА 4: Объём и свечные паттерны ───────────────────────────────────────

def s24_volume_surge_bull(candles, i):
    """
    Объём > 1.8× от среднего за 5 свечей при положительной дельте.
    """
    if i < 5:
        return False
    avg_vol = _avg(candles, i - 1, 5, "volume")
    c       = candles[i]
    return c["volume"] > avg_vol * 1.8 and c["delta"] > 0


def s25_seller_exhaustion(candles, i):
    """
    Аномально высокий sell_vol при бычьем закрытии выше середины —
    продавцы исчерпаны.
    """
    if i < 5:
        return False
    avg_sv = _avg(candles, i - 1, 5, "sell_vol")
    c      = candles[i]
    mid    = (c["high"] + c["low"]) / 2
    return (c["sell_vol"] > avg_sv * 1.8 and
            c["close"] > mid and
            c["close"] > c["open"])


def s26_strong_close(candles, i):
    """
    Сильное закрытие: (close - low) / range > 0.80 при положительной дельте.
    """
    c   = candles[i]
    rng = c["high"] - c["low"]
    if rng <= 0:
        return False
    return (c["close"] - c["low"]) / rng > 0.80 and c["delta"] > 0


def s27_bullish_reversal_candle(candles, i):
    """
    Бычий разворот: предыдущая свеча красная, текущая зелёная
    с более сильной дельтой.
    """
    if i < 1:
        return False
    c = candles[i]
    p = candles[i - 1]
    return (c["close"] > c["open"] and
            p["close"] < p["open"] and
            c["delta"] > 0 and
            c["delta"] > abs(p["delta"]) * 0.5)


def s28_inside_bar_bull_coil(candles, i):
    """
    Inside bar (диапазон внутри предыдущего) + stacked_ask >= 2 —
    пружина перед выстрелом вверх.
    """
    if i < 1:
        return False
    c = candles[i]
    p = candles[i - 1]
    return (c["high"] < p["high"] and
            c["low"]  > p["low"]  and
            c["delta"] > 0 and
            c["stacked_ask"] >= 2)


def s29_range_expansion_bull(candles, i):
    """
    Расширение диапазона > 1.5× среднего + закрытие в верхней трети +
    положительная дельта.
    """
    if i < 5:
        return False
    avg_r = _avg_range(candles, i - 1, 5)
    c     = candles[i]
    rng   = c["high"] - c["low"]
    if rng <= 0:
        return False
    return (rng > avg_r * 1.5 and
            (c["close"] - c["low"]) / rng > 0.70 and
            c["delta"] > 0)


def s30_composite_bullish(candles, i):
    """
    Комплексная стратегия: набирает баллы по 8 критериям,
    сигнал — когда 5 и более совпадают.
    """
    c     = candles[i]
    score = 0

    if c["delta"] > 0:
        score += 1
    if c["volume"] > 0 and c["delta"] / c["volume"] > 0.10:
        score += 1
    if c["stacked_ask"] >= 2:
        score += 1
    if c["poc_pct"] > 0.60:
        score += 1
    if c["close"] > c["open"]:
        score += 1
    if c["buy_vol"] > c["sell_vol"]:
        score += 1
    if i >= 1 and candles[i - 1]["delta"] > 0:
        score += 1
    if c["delta_low"] > 0 and c["delta_high"] > 0:
        score += 1

    return score >= 5


# ════════════════════════════════════════════════════════════════════════════
#  РЕЕСТР ВСЕХ СТРАТЕГИЙ
# ════════════════════════════════════════════════════════════════════════════

ALL_STRATEGIES = [
    ("S01_strong_delta",          s01_strong_buy_delta),
    ("S02_delta_accel",           s02_delta_acceleration),
    ("S03_price_delta_momentum",  s03_price_and_delta_momentum),
    ("S04_delta_trend_3",         s04_delta_trend_3),
    ("S05_delta_turnover",        s05_delta_turnover_bull),
    ("S06_delta_ratio_spike",     s06_delta_ratio_spike),
    ("S07_cum_delta_rising",      s07_cum_delta_rising),
    ("S08_multibar_delta_sum",    s08_multibar_delta_sum),
    ("S09_two_pos_delta",         s09_two_consecutive_positive_delta),
    ("S10_buy_vol_dominance",     s10_high_buy_volume_ratio),
    ("S11_stacked_ask_3",         s11_stacked_ask_imbalances_3),
    ("S12_stacked_ask_2_delta",   s12_stacked_ask_imbalances_2),
    ("S13_ask_imb_vol_surge",     s13_ask_imbalance_with_volume_surge),
    ("S14_ask_imb_at_lows",       s14_ask_imbalance_at_lows),
    ("S15_bid_exhaust_response",  s15_bid_exhaustion_with_ask_response),
    ("S16_poc_breakout",          s16_poc_breakout),
    ("S17_vah_breakout",          s17_vah_breakout),
    ("S18_val_rejection",         s18_val_rejection),
    ("S19_poc_at_high",           s19_poc_at_high),
    ("S20_poc_migration_up",      s20_poc_migration_up),
    ("S21_poc_breakout_stacked",  s21_poc_breakout_with_stacked_ask),
    ("S22_close_above_vah",       s22_close_above_vah),
    ("S23_near_val_with_delta",   s23_price_near_val_with_delta),
    ("S24_volume_surge_bull",     s24_volume_surge_bull),
    ("S25_seller_exhaustion",     s25_seller_exhaustion),
    ("S26_strong_close",          s26_strong_close),
    ("S27_bullish_reversal",      s27_bullish_reversal_candle),
    ("S28_inside_bar_coil",       s28_inside_bar_bull_coil),
    ("S29_range_expansion",       s29_range_expansion_bull),
    ("S30_composite",             s30_composite_bullish),
]
