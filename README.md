# Footprint Backtest — 30 стратегий × 4 таймфрейма

## Структура файлов

```
backtest_strategy_ob_t6/
├── main.py              ← точка входа
├── data_loader.py       ← загрузка Binance + Bybit (день за днём)
├── footprint.py         ← построение footprint (Numba-ядро)
├── strategies.py        ← 30 торговых стратегий
├── backtest.py          ← движок бэктеста и метрики
├── requirements.txt
└── results/             ← создаётся автоматически
    ├── backtest_results.csv
    ├── equity_4h.png
    ├── equity_6h.png
    ├── equity_12h.png
    └── equity_24h.png
```

Данные читаются из:
```
../backtest_strategy_ob_t1/data/binance-f/   ← месячные файлы (BTCUSDT-agg-YYYY-MM.parquet)
../backtest_strategy_ob_t1/data/bybit-f/     ← дневные файлы  (BTCUSDTyyyy-mm-dd.parquet)
```

---

## Установка

```bash
cd ~/worksoft/backtest_strategy_ob_t6
pip install -r requirements.txt
```

---

## Запуск

```bash
python main.py
```

Первый запуск дольше — Numba компилирует JIT-функции (~30 с).
Повторные запуски быстрее (кэш `__pycache__`).

---

## Логика бэктеста

| Шаг | Что происходит |
|-----|----------------|
| Сигнал | Вычисляется на **закрытии** свечи `i` |
| Вход   | По **open** свечи `i+1` |
| Выход  | По **close** свечи `i+1` |
| Комиссия | **0.055%** на вход + **0.055%** на выход = **0.11% roundtrip** |

Только лонг. Каждый сигнал = одна сделка (без накопления позиции).

---

## Таймфреймы

| TF  | Свечей в сутки |
|-----|----------------|
| 4h  | 6              |
| 6h  | 4              |
| 12h | 2              |
| 24h | 1              |

---

## 30 стратегий (краткий обзор)

### Группа 1 — Дельта
| # | Название | Идея |
|---|----------|------|
| S01 | strong_delta | delta/volume > 20% |
| S02 | delta_accel | дельта ускоряется (+30%) |
| S03 | price_delta_momentum | цена↑ + дельта↑ |
| S04 | delta_trend_3 | 3 свечи подряд дельта растёт |
| S05 | delta_turnover | разворот дельты с − на + |
| S06 | delta_ratio_spike | спайк delta/volume vs среднее |
| S07 | cum_delta_rising | накоп. дельта растёт 3 свечи |
| S08 | multibar_delta_sum | сумма 3 дельт > 0, последняя ≥ пред. |
| S09 | two_pos_delta | 2 свечи подряд дельта > 0 |
| S10 | buy_vol_dominance | buy_vol > 60% объёма |

### Группа 2 — Дисбалансы
| # | Название | Идея |
|---|----------|------|
| S11 | stacked_ask_3 | 3+ ask-дисбалансов подряд |
| S12 | stacked_ask_2_delta | 2+ дисбалансов + дельта > 0 |
| S13 | ask_imb_vol_surge | дисбалансы + объём > 1.4× |
| S14 | ask_imb_at_lows | дисбалансы в нижней зоне свечи |
| S15 | bid_exhaust_response | много bid-imb, но дельта > 0 |

### Группа 3 — POC / Value Area
| # | Название | Идея |
|---|----------|------|
| S16 | poc_breakout | close > POC[-1] + дельта |
| S17 | vah_breakout | close > VAH[-1] + дельта |
| S18 | val_rejection | тест VAL + отскок вверх |
| S19 | poc_at_high | POC в верхней части свечи |
| S20 | poc_migration_up | POC растёт 3 свечи подряд |
| S21 | poc_breakout_stacked | pob + stacked_ask≥2 |
| S22 | close_above_vah | close ≥ собственный VAH |
| S23 | near_val_with_delta | close около VAL + дельта > 0 |

### Группа 4 — Объём / свечные паттерны
| # | Название | Идея |
|---|----------|------|
| S24 | volume_surge_bull | объём > 1.8× + дельта |
| S25 | seller_exhaustion | sell_vol спайк, но бычье закрытие |
| S26 | strong_close | (close−low)/range > 80% + дельта |
| S27 | bullish_reversal | красная→зелёная + дельта |
| S28 | inside_bar_coil | inside bar + stacked_ask≥2 |
| S29 | range_expansion | расширение > 1.5× + закрытие вверху |
| S30 | composite | 5+ из 8 бычьих критериев |

---

## Метрики в CSV

| Колонка | Описание |
|---------|----------|
| n_trades | количество сделок |
| win_rate_% | процент прибыльных |
| total_return_% | итоговая доходность |
| sharpe | аннуализированный коэф. Шарпа |
| max_drawdown_% | максимальная просадка |
| profit_factor | gross profit / gross loss |
| avg_pnl_% | средний P&L на сделку |

---

## Часто задаваемые вопросы

**Почему Numba?**  
Обработка 50+ млн тиков требует быстрой математики. Numba компилирует Python-циклы в машинный код — ускорение в 50–200× по сравнению с чистым Python.

**Почему данные читаются по дням?**  
Все файлы Bybit + Binance — ~30 ГБ. Загрузка всего сразу невозможна. Читаем один день, строим свечи, удаляем тики, переходим к следующему дню.

**Как добавить свою стратегию?**  
В файле `strategies.py` добавьте функцию `def s31_my_strategy(candles, i): ...`
и добавьте `("S31_my_strategy", s31_my_strategy)` в список `ALL_STRATEGIES`.
