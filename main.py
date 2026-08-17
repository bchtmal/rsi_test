#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import logging
from logging.handlers import RotatingFileHandler
import ccxt
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import telegram
from telegram.request import HTTPXRequest
from ta.momentum import RSIIndicator
from ta.trend import MACD
import random
import argparse
import datetime
import asyncio

from get_pairs import get_pairs

DATA = {}

# Настройка логирования с файловым обработчиком
def setup_logging():
    """Настройка логирования для записи как в консоль, так и в файл"""
    # Создаём папку logs, если её нет
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Создаём форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Создаём основной логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Удаляем старые обработчики, если они есть
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Файловый обработчик с ротацией (максимум 10MB, хранить 5 резервных копий)
    file_handler = RotatingFileHandler(
        'logs/crypto_signal_bot.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Создаём отдельный файловый обработчик для торговых сигналов
    signal_handler = RotatingFileHandler(
        'logs/trading_signals.log',
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    signal_handler.setLevel(logging.INFO)
    signal_formatter = logging.Formatter(
        '%(asctime)s - SIGNAL - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    signal_handler.setFormatter(signal_formatter)

    # Создаём отдельный логгер для сигналов
    signal_logger = logging.getLogger('trading_signals')
    signal_logger.setLevel(logging.INFO)
    signal_logger.addHandler(signal_handler)
    signal_logger.propagate = False  # Не отправлять родительскому логгеру

    return logger


# Инициализация логирования
logger = setup_logging()

# Загрузка переменных окружения
load_dotenv()

# Получение конфигурации из файла .env
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_PROXY_URL = os.getenv('TELEGRAM_PROXY_URL')  # Переменная окружения для прокси
RSI_WINDOW = int(os.getenv('RSI_WINDOW', 14))
RSI_TIMEFRAME = os.getenv('RSI_TIMEFRAME', '1h')

# Изменение конфигурации для поддержки нескольких торговых пар
TRADING_PAIRS = os.getenv('TRADING_PAIRS', 'BTC/USDT,ETH/USDT,SOL/USDT,SUI/USDT').split(',')
TRADING_PAIRS = get_pairs()


# Уровни RSI для стратегии
RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', 30))
RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', 70))
RSI_EXIT = int(os.getenv('RSI_EXIT', 50))

# Параметры MACD
MACD_FAST = int(os.getenv('MACD_FAST', 12))
MACD_SLOW = int(os.getenv('MACD_SLOW', 26))
MACD_SIGNAL = int(os.getenv('MACD_SIGNAL', 9))

# Настройка режима сигналов
SIGNAL_MODE = os.getenv('SIGNAL_MODE', 'BOTH')  # RSI, MACD, BOTH
RSI_INDEPENDENT = os.getenv('RSI_INDEPENDENT', 'true').lower() == 'true'
MACD_INDEPENDENT = os.getenv('MACD_INDEPENDENT', 'true').lower() == 'true'


class MockBinance:
    """Класс для имитации данных Binance для тестирования"""

    def __init__(self, starting_price=20000, volatility=0.05, timeframe='1h'):
        self.starting_price = starting_price
        self.volatility = volatility
        self.timeframe = timeframe
        self.current_price = starting_price

    def _generate_mock_price(self, periods=100):
        """Генерация имитированных цен по случайной модели"""
        prices = [self.starting_price]

        # Случайный тренд рынка для создания низкого/высокого RSI
        trend_type = random.choice(['uptrend', 'downtrend', 'sideways', 'volatile'])
        logger.info(f"Генерация имитированных данных с трендом: {trend_type}")

        for i in range(1, periods):
            if trend_type == 'uptrend':
                # Восходящий тренд
                change = np.random.normal(0.002, self.volatility)
            elif trend_type == 'downtrend':
                # Нисходящий тренд
                change = np.random.normal(-0.002, self.volatility)
            elif trend_type == 'volatile':
                # Волатильный рынок
                change = np.random.normal(0, self.volatility * 2)
            else:
                # Боковой рынок
                change = np.random.normal(0, self.volatility / 2)

            # Добавление пиков и впадин для чётких сигналов RSI
            if i % 20 == 0 and trend_type == 'volatile':
                if random.random() > 0.5:
                    # Пик цены (может дать сигнал на шорт)
                    change = self.volatility * 3
                else:
                    # Впадина цены (может дать сигнал на лонг)
                    change = -self.volatility * 3

            new_price = prices[-1] * (1 + change)
            prices.append(max(100, new_price))  # Минимальная цена 100

        return prices

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Имитация API fetch_ohlcv Binance"""
        now = datetime.datetime.now()

        # Расчёт интервала на основе таймфрейма
        if timeframe == '1h':
            delta = datetime.timedelta(hours=1)
        elif timeframe == '15m':
            delta = datetime.timedelta(minutes=15)
        elif timeframe == '1d':
            delta = datetime.timedelta(days=1)
        else:
            delta = datetime.timedelta(hours=1)  # По умолчанию 1h

        # Генерация имитированных цен
        prices = self._generate_mock_price(limit)

        # Формирование данных OHLCV
        ohlcv_data = []
        for i in range(limit):
            timestamp = int((now - delta * (limit - i - 1)).timestamp() * 1000)
            price = prices[i]

            # Генерация O, H, L на основе цены закрытия
            open_price = price * (1 + np.random.normal(0, 0.005))
            high_price = max(price, open_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(price, open_price) * (1 - abs(np.random.normal(0, 0.01)))
            volume = price * np.random.uniform(10, 100)

            ohlcv_data.append([timestamp, open_price, high_price, low_price, price, volume])

        return ohlcv_data


class CryptoSignalBot:
    def __init__(self, symbol, use_mock=False):
        self.symbol = symbol
        self.use_mock = use_mock
        self.exchange = self._init_exchange()
        self.bot = self._init_telegram_bot()
        self.last_alert_time = 0
        self.alert_cooldown = 3600  # 1 час кулдауна между оповещениями
        self.current_position = None  # None = нет позиции, 'long' = в лонге, 'short' = в шорте
        self.mock_speed = 60  # Скорость работы в 5 раз быстрее при использовании mock

        # Добавляем переменные для расчёта PnL
        self.position_size = 100  # USD
        self.leverage = 20
        self.entry_price = None
        self.entry_time = None
        self.total_pnl = 0  # Общий накопленный PnL
        self.trade_count = 0  # Количество совершённых сделок
        self.winning_trades = 0  # Количество прибыльных сделок

        # Переменная для хранения ID сообщения
        self.entry_message_id = None  # Сохраняем ID сообщения при открытии позиции

        # Настройка режима сигналов
        self.signal_mode = SIGNAL_MODE
        self.rsi_independent = RSI_INDEPENDENT
        self.macd_independent = MACD_INDEPENDENT

    def _init_exchange(self):
        """Инициализация подключения к бирже Binance или mock Binance"""
        try:
            if self.use_mock:
                logger.info("Использование имитированных данных для тестирования")
                return MockBinance(starting_price=20000, volatility=0.05, timeframe=RSI_TIMEFRAME)
            else:
                exchange = ccxt.binance({
                    'apiKey': BINANCE_API_KEY,
                    'secret': BINANCE_SECRET_KEY,
                    'enableRateLimit': True,
                })
                logger.info(f"Успешное подключение к Binance")
                return exchange
        except Exception as e:
            logger.error(f"Ошибка подключения к Binance: {e}")
            raise

    def _init_telegram_bot(self):
        return
        """Инициализация Telegram бота с поддержкой прокси"""
        try:
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                logger.warning("Отсутствует TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID в переменных окружения.")
                raise ValueError("Отсутствует конфигурация Telegram")

            # Создаём запрос с прокси, если он указан
            if TELEGRAM_PROXY_URL:
                request = HTTPXRequest(proxy=TELEGRAM_PROXY_URL)
                bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN, request=request)
                logger.info(
                    f"Успешное подключение к Telegram боту через прокси: {TELEGRAM_PROXY_URL}, Chat ID: {TELEGRAM_CHAT_ID}")
            else:
                bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
                logger.info(f"Успешное подключение к Telegram боту (без прокси), Chat ID: {TELEGRAM_CHAT_ID}")

            return bot
        except Exception as e:
            logger.error(f"Ошибка подключения к Telegram: {e}")
            raise

    def fetch_ohlcv_data(self, timeframe=RSI_TIMEFRAME, limit=100):
        """Получение данных цен с Binance"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Ошибка получения данных OHLCV для {self.symbol}: {e}")
            return None

    def calculate_rsi(self, df, window=RSI_WINDOW):
        """Расчёт индикатора RSI из данных цен"""
        if df is None or len(df) < window:
            return None

        try:
            rsi_indicator = RSIIndicator(close=df['close'], window=window)
            df['rsi'] = rsi_indicator.rsi()
            return df
        except Exception as e:
            logger.error(f"Ошибка расчёта RSI: {e}")
            return None

    def calculate_macd(self, df, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
        """Расчёт индикатора MACD из данных цен"""
        if df is None or len(df) < slow:
            return None

        try:
            macd_indicator = MACD(
                close=df['close'],
                window_fast=fast,
                window_slow=slow,
                window_sign=signal
            )
            df['macd'] = macd_indicator.macd()
            df['macd_signal'] = macd_indicator.macd_signal()
            df['macd_histogram'] = macd_indicator.macd_diff()
            return df
        except Exception as e:
            logger.error(f"Ошибка расчёта MACD: {e}")
            return None

    def calculate_pnl(self, entry_price, exit_price, position_type):
        """Расчёт PnL с плечом x20"""
        if entry_price is None or exit_price is None:
            return 0

        # Расчёт процентного изменения цены
        if position_type == 'long':
            price_change_percent = (exit_price - entry_price) / entry_price
        elif position_type == 'short':
            price_change_percent = (entry_price - exit_price) / entry_price
        else:
            return 0

        # Применение плеча
        leveraged_return = price_change_percent * self.leverage

        # Расчёт PnL в USD
        pnl_usd = self.position_size * leveraged_return

        return pnl_usd

    def get_current_pnl(self, current_price):
        """Расчёт текущего PnL открытой позиции"""
        if self.entry_price is None or self.current_position not in ['long', 'short']:
            return 0

        return self.calculate_pnl(self.entry_price, current_price, self.current_position)

    def check_rsi_signal(self, df):
        """Проверка независимого сигнала RSI"""
        if df is None or 'rsi' not in df.columns:
            return None

        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]

        if np.isnan(latest_rsi):
            return None

        current_time = time.time()
        cooldown_time = self.alert_cooldown / self.mock_speed if self.use_mock else self.alert_cooldown

        # Сигнал RSI на лонг
        if latest_rsi < RSI_OVERSOLD:
            if current_time - self.last_alert_time > cooldown_time:
                return {
                    'signal_type': 'rsi',
                    'signal': 'long',
                    'rsi': latest_rsi,
                    'price': latest_close,
                    'trigger': 'rsi_oversold',
                    'position_size': self.position_size,
                    'leverage': self.leverage
                }

        # Сигнал RSI на шорт
        elif latest_rsi > RSI_OVERBOUGHT:
            if current_time - self.last_alert_time > cooldown_time:
                return {
                    'signal_type': 'rsi',
                    'signal': 'short',
                    'rsi': latest_rsi,
                    'price': latest_close,
                    'trigger': 'rsi_overbought',
                    'position_size': self.position_size,
                    'leverage': self.leverage
                }

        return None

    def check_macd_signal(self, df):
        """Проверка независимого сигнала MACD"""
        if df is None or 'macd' not in df.columns or len(df) < 2:
            return None

        latest_macd = df['macd'].iloc[-1]
        latest_macd_signal = df['macd_signal'].iloc[-1]
        latest_close = df['close'].iloc[-1]

        prev_macd = df['macd'].iloc[-2]
        prev_macd_signal = df['macd_signal'].iloc[-2]

        if any(np.isnan([latest_macd, latest_macd_signal, prev_macd, prev_macd_signal])):
            return None

        current_time = time.time()
        cooldown_time = self.alert_cooldown / self.mock_speed if self.use_mock else self.alert_cooldown

        # Бычий crossover MACD
        if (prev_macd <= prev_macd_signal) and (latest_macd > latest_macd_signal):
            if current_time - self.last_alert_time > cooldown_time:
                return {
                    'signal_type': 'macd',
                    'signal': 'long',
                    'macd': latest_macd,
                    'macd_signal': latest_macd_signal,
                    'macd_histogram': df['macd_histogram'].iloc[-1],
                    'price': latest_close,
                    'trigger': 'macd_bullish_cross',
                    'position_size': self.position_size,
                    'leverage': self.leverage
                }

        # Медвежий crossover MACD
        elif (prev_macd >= prev_macd_signal) and (latest_macd < latest_macd_signal):
            if current_time - self.last_alert_time > cooldown_time:
                return {
                    'signal_type': 'macd',
                    'signal': 'short',
                    'macd': latest_macd,
                    'macd_signal': latest_macd_signal,
                    'macd_histogram': df['macd_histogram'].iloc[-1],
                    'price': latest_close,
                    'trigger': 'macd_bearish_cross',
                    'position_size': self.position_size,
                    'leverage': self.leverage
                }

        return None

    def get_reference_signals(self, df, exclude_type=None):
        """Получение состояния других сигналов для отображения в качестве справки"""
        reference = {}

        if exclude_type != 'rsi' and 'rsi' in df.columns:
            latest_rsi = df['rsi'].iloc[-1]
            if not np.isnan(latest_rsi):
                if latest_rsi < RSI_OVERSOLD:
                    rsi_status = "Перепроданность (Сигнал на лонг)"
                elif latest_rsi > RSI_OVERBOUGHT:
                    rsi_status = "Перекупленность (Сигнал на шорт)"
                else:
                    rsi_status = "Нейтрально"
                reference['rsi'] = {'value': latest_rsi, 'status': rsi_status}

        if exclude_type != 'macd' and 'macd' in df.columns and len(df) >= 2:
            latest_macd = df['macd'].iloc[-1]
            latest_macd_signal = df['macd_signal'].iloc[-1]

            if not any(np.isnan([latest_macd, latest_macd_signal])):
                if latest_macd > latest_macd_signal:
                    macd_status = "Бычий (Восходящий тренд)"
                else:
                    macd_status = "Медвежий (Нисходящий тренд)"
                reference['macd'] = {
                    'macd': latest_macd,
                    'signal': latest_macd_signal,
                    'status': macd_status
                }

        return reference

    def check_entry_conditions(self, df):
        """Проверка условий входа с независимыми сигналами"""
        if df is None:
            return None

        # Сначала проверяем условия выхода
        if self.current_position in ['long', 'short']:
            return self._check_exit_conditions(df)

        # Проверяем новые сигналы на вход
        signals_to_check = []

        if self.signal_mode in ['RSI', 'BOTH'] and self.rsi_independent:
            rsi_signal = self.check_rsi_signal(df)
            if rsi_signal:
                signals_to_check.append(rsi_signal)

        if self.signal_mode in ['MACD', 'BOTH'] and self.macd_independent:
            macd_signal = self.check_macd_signal(df)
            if macd_signal:
                signals_to_check.append(macd_signal)

        # Возвращаем первый активированный сигнал
        if signals_to_check:
            selected_signal = signals_to_check[0]  # Можно добавить логику приоритета

            # Добавляем справочную информацию о других сигналах
            reference_signals = self.get_reference_signals(df, exclude_type=selected_signal['signal_type'])
            selected_signal['reference_signals'] = reference_signals

            # Сохраняем информацию о входе
            self.entry_price = selected_signal['price']
            self.entry_time = time.time()
            self.last_alert_time = time.time()

            return selected_signal

        # Логируем текущие значения индикаторов
        if 'rsi' in df.columns:
            latest_rsi = df['rsi'].iloc[-1]
            latest_close = df['close'].iloc[-1]

            macd_info = ""
            if 'macd' in df.columns:
                latest_macd = df['macd'].iloc[-1]
                latest_macd_signal = df['macd_signal'].iloc[-1]
                latest_macd_histogram = df['macd_histogram'].iloc[-1]
                if not np.isnan(latest_macd):
                    macd_info = f" | MACD: {latest_macd:.4f} | Signal: {latest_macd_signal:.4f} | Histogram: {latest_macd_histogram:.4f}"

            if not np.isnan(latest_rsi):
                logger.info(f"Индикаторы {self.symbol}: RSI: {latest_rsi:.2f}{macd_info}")
                DATA[self.symbol] = latest_rsi


            # Если есть открытая позиция, добавляем информацию о текущем PnL
            if self.current_position in ['long', 'short'] and self.entry_price is not None:
                current_pnl = self.get_current_pnl(latest_close)
                logger.info(f"Текущий PnL для {self.symbol}: ${current_pnl:.2f}")

        return None

    def _check_exit_conditions(self, df):
        """Проверка условий выхода из позиции"""
        if df is None or 'rsi' not in df.columns:
            return None

        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        current_time = time.time()
        cooldown_time = self.alert_cooldown / self.mock_speed if self.use_mock else self.alert_cooldown

        if self.current_position == 'long' and latest_rsi > RSI_EXIT:
            if current_time - self.last_alert_time > cooldown_time:
                pnl = self.calculate_pnl(self.entry_price, latest_close, 'long')
                self.total_pnl += pnl
                self.trade_count += 1
                if pnl > 0:
                    self.winning_trades += 1

                self.last_alert_time = current_time
                return {
                    'signal': 'exit_long',
                    'rsi': latest_rsi,
                    'price': latest_close,
                    'entry_price': self.entry_price,
                    'pnl': pnl,
                    'total_pnl': self.total_pnl,
                    'trade_count': self.trade_count,
                    'win_rate': (self.winning_trades / self.trade_count) * 100
                }

        elif self.current_position == 'short' and latest_rsi < RSI_EXIT:
            if current_time - self.last_alert_time > cooldown_time:
                pnl = self.calculate_pnl(self.entry_price, latest_close, 'short')
                self.total_pnl += pnl
                self.trade_count += 1
                if pnl > 0:
                    self.winning_trades += 1

                self.last_alert_time = current_time
                return {
                    'signal': 'exit_short',
                    'rsi': latest_rsi,
                    'price': latest_close,
                    'entry_price': self.entry_price,
                    'pnl': pnl,
                    'total_pnl': self.total_pnl,
                    'trade_count': self.trade_count,
                    'win_rate': (self.winning_trades / self.trade_count) * 100
                }

        return None

    async def send_telegram_alert(self, signal_data):
        """Отправка оповещения через Telegram"""
        return
        try:
            coin_name = self.symbol.split('/')[0]
            signal = signal_data['signal']
            rsi_value = signal_data['rsi']
            price = signal_data['price']

            # Получаем логгер сигналов
            signal_logger = logging.getLogger('trading_signals')

            # Разделяем chat_id и message_thread_id, если они указаны
            if '_' in TELEGRAM_CHAT_ID:
                chat_id, message_thread_id = TELEGRAM_CHAT_ID.split('_')
                message_thread_id = int(message_thread_id)
            else:
                chat_id = TELEGRAM_CHAT_ID
                message_thread_id = None

            if signal == 'long':
                signal_type = signal_data.get('signal_type', 'combined')
                trigger = signal_data.get('trigger', '')
                position_size = signal_data['position_size']
                leverage = signal_data['leverage']

                if signal_type == 'rsi':
                    rsi_value = signal_data['rsi']
                    message = (f"🚨 СИГНАЛ НА ЛОНГ (RSI): {coin_name} по цене ${price:.2f}\n"
                               f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_OVERSOLD} → Перепроданность (oversold)\n")

                elif signal_type == 'macd':
                    macd = signal_data['macd']
                    macd_signal_val = signal_data['macd_signal']
                    macd_histogram = signal_data['macd_histogram']
                    message = (f"🚨 СИГНАЛ НА ЛОНГ (MACD): {coin_name} по цене ${price:.2f}\n"
                               f"📈 MACD ({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) = {macd:.4f} пересекает вверх {macd_signal_val:.4f} → Бычий сигнал\n"
                               f"📊 Гистограмма = {macd_histogram:.4f}\n")
                else:
                    # Запасной вариант для старого формата
                    rsi_value = signal_data.get('rsi', 0)
                    message = (f"🚨 СИГНАЛ НА ЛОНГ: {coin_name} по цене ${price:.2f}\n"
                               f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_OVERSOLD} → Перепроданность (oversold)\n")

                # Добавляем справочную информацию
                if 'reference_signals' in signal_data:
                    ref = signal_data['reference_signals']
                    if 'rsi' in ref and signal_type != 'rsi':
                        message += f"📊 Справочный RSI: {ref['rsi']['value']:.2f} - {ref['rsi']['status']}\n"
                    if 'macd' in ref and signal_type != 'macd':
                        message += f"📈 Справочный MACD: {ref['macd']['macd']:.4f} - {ref['macd']['status']}\n"

                message += (f"👉 Рекомендация: ПОКУПКА (ЛОНГ)\n"
                            f"💰 Позиция: ${position_size} с плечом x{leverage}\n"
                            f"🔄 Закрытие при RSI > {RSI_EXIT}")

                self.current_position = 'long'

                # Логируем сигнал
                signal_logger.info(
                    f"LONG_ENTRY_{signal_type.upper()} | {coin_name} | Price: ${price:.2f} | Trigger: {trigger} | Size: ${position_size} | Leverage: x{leverage}")

                # Отправляем сообщение и сохраняем ID
                if message_thread_id:
                    sent_message = await self.bot.send_message(
                        chat_id=int(chat_id),
                        text=message,
                        message_thread_id=message_thread_id
                    )
                else:
                    sent_message = await self.bot.send_message(
                        chat_id=int(chat_id),
                        text=message
                    )

                # Сохраняем ID сообщения для последующего ответа
                self.entry_message_id = sent_message.message_id

            elif signal == 'short':
                signal_type = signal_data.get('signal_type', 'combined')
                trigger = signal_data.get('trigger', '')
                position_size = signal_data['position_size']
                leverage = signal_data['leverage']

                if signal_type == 'rsi':
                    rsi_value = signal_data['rsi']
                    message = (f"🚨 СИГНАЛ НА ШОРТ (RSI): {coin_name} по цене ${price:.2f}\n"
                               f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_OVERBOUGHT} → Перекупленность (overbought)\n")

                elif signal_type == 'macd':
                    macd = signal_data['macd']
                    macd_signal_val = signal_data['macd_signal']
                    macd_histogram = signal_data['macd_histogram']
                    message = (f"🚨 СИГНАЛ НА ШОРТ (MACD): {coin_name} по цене ${price:.2f}\n"
                               f"📉 MACD ({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) = {macd:.4f} пересекает вниз {macd_signal_val:.4f} → Медвежий сигнал\n"
                               f"📊 Гистограмма = {macd_histogram:.4f}\n")
                else:
                    # Запасной вариант для старого формата
                    rsi_value = signal_data.get('rsi', 0)
                    message = (f"🚨 СИГНАЛ НА ШОРТ: {coin_name} по цене ${price:.2f}\n"
                               f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_OVERBOUGHT} → Перекупленность (overbought)\n")

                # Добавляем справочную информацию
                if 'reference_signals' in signal_data:
                    ref = signal_data['reference_signals']
                    if 'rsi' in ref and signal_type != 'rsi':
                        message += f"📊 Справочный RSI: {ref['rsi']['value']:.2f} - {ref['rsi']['status']}\n"
                    if 'macd' in ref and signal_type != 'macd':
                        message += f"📉 Справочный MACD: {ref['macd']['macd']:.4f} - {ref['macd']['status']}\n"

                message += (f"👉 Рекомендация: КОРОТКАЯ ПРОДАЖА (ШОРТ)\n"
                            f"💰 Позиция: ${position_size} с плечом x{leverage}\n"
                            f"🔄 Закрытие при RSI < {RSI_EXIT}")

                self.current_position = 'short'

                # Логируем сигнал
                signal_logger.info(
                    f"SHORT_ENTRY_{signal_type.upper()} | {coin_name} | Price: ${price:.2f} | Trigger: {trigger} | Size: ${position_size} | Leverage: x{leverage}")

                # Отправляем сообщение и сохраняем ID
                if message_thread_id:
                    sent_message = await self.bot.send_message(
                        chat_id=int(chat_id),
                        text=message,
                        message_thread_id=message_thread_id
                    )
                else:
                    sent_message = await self.bot.send_message(
                        chat_id=int(chat_id),
                        text=message
                    )

                # Сохраняем ID сообщения для последующего ответа
                self.entry_message_id = sent_message.message_id

            elif signal == 'exit_long':
                entry_price = signal_data['entry_price']
                pnl = signal_data['pnl']
                total_pnl = signal_data['total_pnl']
                trade_count = signal_data['trade_count']
                win_rate = signal_data['win_rate']

                pnl_emoji = "💚" if pnl > 0 else "❤️"
                price_change = ((price - entry_price) / entry_price) * 100

                message = (f"🔔 СИГНАЛ НА ВЫХОД ИЗ ЛОНГА: {coin_name}\n"
                           f"📈 Цена входа: ${entry_price:.2f} → Цена выхода: ${price:.2f}\n"
                           f"📊 Изменение цены: {price_change:+.2f}%\n"
                           f"RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_EXIT}\n"
                           f"👉 Рекомендация: ЗАКРЫТЬ ЛОНГ\n"
                           f"{pnl_emoji} PnL этой сделки: ${pnl:+.2f}\n"
                           f"💰 Общий PnL: ${total_pnl:+.2f}\n"
                           f"📈 Сделок: {trade_count} | Процент выигрышей: {win_rate:.1f}%")
                self.current_position = 'exit_long'

                # Логируем сигнал в отдельный файл
                signal_logger.info(
                    f"LONG_EXIT | {coin_name} | Entry: ${entry_price:.2f} | Exit: ${price:.2f} | PnL: ${pnl:+.2f} | Total_PnL: ${total_pnl:+.2f} | Win_Rate: {win_rate:.1f}%")

                # Отвечаем на сообщение открытия позиции, если оно есть
                if self.entry_message_id:
                    if message_thread_id:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            message_thread_id=message_thread_id,
                            reply_to_message_id=self.entry_message_id
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            reply_to_message_id=self.entry_message_id
                        )
                else:
                    # Если ID сообщения нет, отправляем обычное сообщение
                    if message_thread_id:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            message_thread_id=message_thread_id
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message
                        )

                # Сбрасываем цену входа и ID сообщения после закрытия позиции
                self.entry_price = None
                self.entry_time = None
                self.entry_message_id = None

            elif signal == 'exit_short':
                entry_price = signal_data['entry_price']
                pnl = signal_data['pnl']
                total_pnl = signal_data['total_pnl']
                trade_count = signal_data['trade_count']
                win_rate = signal_data['win_rate']

                pnl_emoji = "💚" if pnl > 0 else "❤️"
                price_change = ((entry_price - price) / entry_price) * 100

                message = (f"🔔 СИГНАЛ НА ВЫХОД ИЗ ШОРТА: {coin_name}\n"
                           f"📉 Цена входа: ${entry_price:.2f} → Цена выхода: ${price:.2f}\n"
                           f"📊 Изменение цены: {price_change:+.2f}% (для шорта)\n"
                           f"RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_EXIT}\n"
                           f"👉 Рекомендация: ЗАКРЫТЬ ШОРТ\n"
                           f"{pnl_emoji} PnL этой сделки: ${pnl:+.2f}\n"
                           f"💰 Общий PnL: ${total_pnl:+.2f}\n"
                           f"📈 Сделок: {trade_count} | Процент выигрышей: {win_rate:.1f}%")
                self.current_position = 'exit_short'

                # Логируем сигнал в отдельный файл
                signal_logger.info(
                    f"SHORT_EXIT | {coin_name} | Entry: ${entry_price:.2f} | Exit: ${price:.2f} | PnL: ${pnl:+.2f} | Total_PnL: ${total_pnl:+.2f} | Win_Rate: {win_rate:.1f}%")

                # Отвечаем на сообщение открытия позиции, если оно есть
                if self.entry_message_id:
                    if message_thread_id:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            message_thread_id=message_thread_id,
                            reply_to_message_id=self.entry_message_id
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            reply_to_message_id=self.entry_message_id
                        )
                else:
                    # Если ID сообщения нет, отправляем обычное сообщение
                    if message_thread_id:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message,
                            message_thread_id=message_thread_id
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=int(chat_id),
                            text=message
                        )

                # Сбрасываем цену входа и ID сообщения после закрытия позиции
                self.entry_price = None
                self.entry_time = None
                self.entry_message_id = None

            logger.info(f"Отправлено оповещение {signal} в Telegram для {self.symbol}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки оповещения в Telegram для {self.symbol}: {e}")
            return False


    async def run(self):
        """Запуск бота"""
        logger.info(f"Запуск бота мониторинга RSI + MACD для {self.symbol} со стратегией Long/Short")
        # logger.info(
        #     f"Стратегия RSI: Лонг при RSI < {RSI_OVERSOLD}, Шорт при RSI > {RSI_OVERBOUGHT}, Выход при RSI = {RSI_EXIT}")
        # logger.info(
        #     f"Стратегия MACD: Комбинирование с сигналами кроссовера и дивергенции MACD (Параметры: {MACD_FAST},{MACD_SLOW},{MACD_SIGNAL})")
        # logger.info(f"Конфигурация торговли: Позиция ${self.position_size} с плечом x{self.leverage}")

        # Получаем информацию о чате при запуске бота
        await self.get_chat_info()

        try:
            while True:
                # Получаем данные
                df = self.fetch_ohlcv_data()

                # Рассчитываем RSI
                df = self.calculate_rsi(df)

                # Рассчитываем MACD
                df = self.calculate_macd(df)

                # Проверяем условия
                signal_data = self.check_entry_conditions(df)
                if signal_data:
                    await self.send_telegram_alert(signal_data)

                # Периодически отображаем статистику торговли
                if self.trade_count > 0:
                    win_rate = (self.winning_trades / self.trade_count) * 100
                    logger.info(f"📊 Статистика {self.symbol}: {self.trade_count} сделок | "
                                f"Процент выигрышей: {win_rate:.1f}% | Общий PnL: ${self.total_pnl:+.2f}")

                # Ожидание перед следующей проверкой (5 минут в реальном времени или быстрее при использовании mock)
                sleep_time = 300 / self.mock_speed if self.use_mock else 300
                logger.info(f"Ожидание {sleep_time:.1f} секунд перед следующей проверкой {self.symbol}...")
                print([(item[0], int(item[1])) for item in sorted(DATA.items(), key=lambda x: -x[1])])
                break # остановка после одного цикла
                await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info(f"Бот для {self.symbol} остановлен пользователем")
            # Отображаем итоговую статистику
            if self.trade_count > 0:
                win_rate = (self.winning_trades / self.trade_count) * 100
                logger.info(f"📊 Итоговая статистика {self.symbol}: {self.trade_count} сделок | "
                            f"Процент выигрышей: {win_rate:.1f}% | Общий PnL: ${self.total_pnl:+.2f}")
        except Exception as e:
            logger.error(f"Необработанная ошибка для {self.symbol}: {e}")

    def get_trading_stats(self):
        """Получение статистики торговли"""
        win_rate = (self.winning_trades / self.trade_count) * 100 if self.trade_count > 0 else 0
        return {
            'symbol': self.symbol,
            'total_trades': self.trade_count,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'current_position': self.current_position,
            'entry_price': self.entry_price,
            'entry_message_id': self.entry_message_id
        }

    async def get_chat_info(self):
        return
        """Получение и логирование детальной информации о чате"""
        try:
            # Разделяем chat_id и message_thread_id, если они указаны
            if '_' in TELEGRAM_CHAT_ID:
                chat_id, message_thread_id = TELEGRAM_CHAT_ID.split('_')
                chat_id = int(chat_id)
                message_thread_id = int(message_thread_id)
            else:
                chat_id = int(TELEGRAM_CHAT_ID)
                message_thread_id = None

            # Получаем информацию о чате
            chat_info = await self.bot.get_chat(chat_id)

            # Логируем детальную информацию
            logger.info(f"📋 Информация о чате:")
            logger.info(f"   - ID: {chat_info.id}")
            logger.info(f"   - Тип: {chat_info.type}")

            if chat_info.title:
                logger.info(f"   - Название: {chat_info.title}")
            if chat_info.username:
                logger.info(f"   - Имя пользователя: @{chat_info.username}")
            if chat_info.first_name:
                logger.info(f"   - Имя: {chat_info.first_name}")
            if chat_info.last_name:
                logger.info(f"   - Фамилия: {chat_info.last_name}")
            if chat_info.description:
                logger.info(f"   - Описание: {chat_info.description}")

            if message_thread_id:
                logger.info(f"   - ID ветки сообщений: {message_thread_id}")

            # Проверяем права бота в группе/канале
            if chat_info.type in ['group', 'supergroup', 'channel']:
                try:
                    bot_member = await self.bot.get_chat_member(chat_id, self.bot.id)
                    logger.info(f"   - Статус бота: {bot_member.status}")
                    if hasattr(bot_member, 'can_post_messages'):
                        logger.info(f"   - Может отправлять сообщения: {bot_member.can_post_messages}")
                except Exception as e:
                    logger.warning(f"   - Не удалось получить информацию о правах бота: {e}")

        except Exception as e:
            logger.warning(f"Не удалось получить детальную информацию о чате {TELEGRAM_CHAT_ID}: {e}")


class MultiPairSignalBot:
    def __init__(self, trading_pairs, use_mock=False):
        self.trading_pairs = trading_pairs
        self.use_mock = use_mock
        self.bots = {}
        self._init_bots()

    def _init_bots(self):
        """Инициализация ботов для каждой торговой пары"""
        for pair in self.trading_pairs:
            self.bots[pair] = CryptoSignalBot(symbol=pair, use_mock=self.use_mock)
            logger.info(f"Инициализирован бот для {pair}")

    def get_combined_stats(self):
        """Получение сводной статистики от всех ботов"""
        total_trades = 0
        total_winning_trades = 0
        total_pnl = 0
        active_positions = 0

        stats_by_pair = {}

        for pair, bot in self.bots.items():
            pair_stats = bot.get_trading_stats()
            stats_by_pair[pair] = pair_stats

            total_trades += pair_stats['total_trades']
            total_winning_trades += pair_stats['winning_trades']
            total_pnl += pair_stats['total_pnl']

            if pair_stats['current_position'] in ['long', 'short']:
                active_positions += 1

        overall_win_rate = (total_winning_trades / total_trades) * 100 if total_trades > 0 else 0

        return {
            'total_trades': total_trades,
            'total_winning_trades': total_winning_trades,
            'overall_win_rate': overall_win_rate,
            'total_pnl': total_pnl,
            'active_positions': active_positions,
            'stats_by_pair': stats_by_pair
        }

    def log_combined_stats(self):
        """Отображение сводной статистики"""
        stats = self.get_combined_stats()

        logger.info("=" * 60)
        logger.info("📊 СВОДНАЯ СТАТИСТИКА ПО ВСЕМ ТОРГОВЫМ ПАРАМ")
        logger.info(f"💰 Общий PnL: ${stats['total_pnl']:+.2f}")
        logger.info(f"📈 Всего сделок: {stats['total_trades']}")
        logger.info(f"🎯 Общий процент выигрышей: {stats['overall_win_rate']:.1f}%")
        logger.info(f"🔄 Открытых позиций: {stats['active_positions']}")

        logger.info("\n📋 Детали по каждой паре:")
        for pair, pair_stats in stats['stats_by_pair'].items():
            status = ""
            if pair_stats['current_position'] in ['long', 'short']:
                status = f" (Открыт {pair_stats['current_position'].upper()} по ${pair_stats['entry_price']:.2f})"

            logger.info(f"  {pair}: {pair_stats['total_trades']} сделок | "
                        f"Выигрышей {pair_stats['win_rate']:.1f}% | "
                        f"PnL: ${pair_stats['total_pnl']:+.2f}{status}")
        logger.info("=" * 60)

    async def run_all(self):
        """Запуск всех ботов одновременно"""
        try:
            # Создаём список корутин для запуска
            tasks = [bot.run() for bot in self.bots.values()]
            # Запускаем все боты одновременно
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Все боты остановлены пользователем")
            # Отображаем итоговую статистику
            self.log_combined_stats()
        except Exception as e:
            logger.error(f"Ошибка при запуске нескольких ботов: {e}")
            self.log_combined_stats()


if __name__ == "__main__":
    # Добавляем параметры для выбора режима реальный/mock
    parser = argparse.ArgumentParser(description='Крипто-сигнальный бот со стратегией Long/Short на основе RSI')
    parser.add_argument('--mock', action='store_true', help='Запуск с имитированными данными для тестирования')
    args = parser.parse_args()

    # Логируем информацию о запуске
    logger.info("=" * 80)
    logger.info("🚀 ЗАПУСК CRYPTO SIGNAL BOT")
    logger.info("=" * 80)
    logger.info(f"📁 Лог-файлы сохраняются в:")
    logger.info(f"   - Общий: logs/crypto_signal_bot.log")
    logger.info(f"   - Торговые сигналы: logs/trading_signals.log")
    logger.info(f"🔧 Режим: {'Mock (Тестирование)' if args.mock else 'Live Trading'}")
    logger.info(
        f"🎯 Режим сигналов: {SIGNAL_MODE} | RSI независим: {RSI_INDEPENDENT} | MACD независим: {MACD_INDEPENDENT}")
    logger.info(f"📊 Торговые пары: {', '.join(TRADING_PAIRS)}")
    logger.info(f"⚙️  Конфигурация RSI: Window={RSI_WINDOW}, Timeframe={RSI_TIMEFRAME}")
    logger.info(f"📈 Уровни RSI: Перепроданность<{RSI_OVERSOLD}, Перекупленность>{RSI_OVERBOUGHT}, Выход={RSI_EXIT}")
    logger.info(f"📊 Конфигурация MACD: Fast={MACD_FAST}, Slow={MACD_SLOW}, Signal={MACD_SIGNAL}")
    logger.info("=" * 80)

    # Логируем сигнал запуска в файл торговых сигналов
    signal_logger = logging.getLogger('trading_signals')
    signal_logger.info(
        f"BOT_START | Mode: {'Mock' if args.mock else 'Live'} | Pairs: {','.join(TRADING_PAIRS)} | RSI_Config: {RSI_WINDOW}_{RSI_TIMEFRAME}_{RSI_OVERSOLD}_{RSI_OVERBOUGHT}_{RSI_EXIT} | MACD_Config: {MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}")

    try:
        multi_bot = MultiPairSignalBot(trading_pairs=TRADING_PAIRS, use_mock=args.mock)
        asyncio.run(multi_bot.run_all())
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        signal_logger.info(f"BOT_ERROR | Error: {str(e)}")
    finally:
        logger.info("🛑 Бот полностью остановлен")
        signal_logger.info("BOT_STOP | Bot stopped")