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

# Thiết lập logging với file handler
def setup_logging():
    """Thiết lập logging để ghi vào cả console và file"""
    # Tạo thư mục logs nếu chưa tồn tại
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Tạo formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Tạo logger chính
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Xóa các handler cũ nếu có
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler với rotation (tối đa 10MB, giữ 5 file backup)
    file_handler = RotatingFileHandler(
        'logs/crypto_signal_bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Tạo file handler riêng cho trading signals
    signal_handler = RotatingFileHandler(
        'logs/trading_signals.log',
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    signal_handler.setLevel(logging.INFO)
    signal_formatter = logging.Formatter(
        '%(asctime)s - SIGNAL - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    signal_handler.setFormatter(signal_formatter)
    
    # Tạo logger riêng cho signals
    signal_logger = logging.getLogger('trading_signals')
    signal_logger.setLevel(logging.INFO)
    signal_logger.addHandler(signal_handler)
    signal_logger.propagate = False  # Không gửi lên parent logger
    
    return logger

# Khởi tạo logging
logger = setup_logging()

# Load biến môi trường
load_dotenv()

# Lấy thông tin cấu hình từ file .env
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_PROXY_URL = os.getenv('TELEGRAM_PROXY_URL')  # Thêm biến môi trường cho proxy
RSI_WINDOW = int(os.getenv('RSI_WINDOW', 14))
RSI_TIMEFRAME = os.getenv('RSI_TIMEFRAME', '1h')

# Thay đổi cấu hình để hỗ trợ nhiều cặp giao dịch
TRADING_PAIRS = os.getenv('TRADING_PAIRS', 'BTC/USDT,ETH/USDT,SOL/USDT,SUI/USDT').split(',')

# Các ngưỡng RSI cho chiến lược
RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', 30))
RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', 70))
RSI_EXIT = int(os.getenv('RSI_EXIT', 50))

# Các thông số MACD
MACD_FAST = int(os.getenv('MACD_FAST', 12))
MACD_SLOW = int(os.getenv('MACD_SLOW', 26))
MACD_SIGNAL = int(os.getenv('MACD_SIGNAL', 9))

# Cấu hình signal mode
SIGNAL_MODE = os.getenv('SIGNAL_MODE', 'BOTH')  # RSI, MACD, BOTH
RSI_INDEPENDENT = os.getenv('RSI_INDEPENDENT', 'true').lower() == 'true'
MACD_INDEPENDENT = os.getenv('MACD_INDEPENDENT', 'true').lower() == 'true'

class MockBinance:
    """Class giả lập dữ liệu từ Binance cho việc test"""
    
    def __init__(self, starting_price=20000, volatility=0.05, timeframe='1h'):
        self.starting_price = starting_price
        self.volatility = volatility
        self.timeframe = timeframe
        self.current_price = starting_price
        
    def _generate_mock_price(self, periods=100):
        """Tạo giá giả lập theo mô hình ngẫu nhiên"""
        prices = [self.starting_price]
        
        # Tạo một xu hướng thị trường ngẫu nhiên để tạo ra RSI thấp/cao
        trend_type = random.choice(['uptrend', 'downtrend', 'sideways', 'volatile'])
        logger.info(f"Tạo dữ liệu giả lập với xu hướng: {trend_type}")
        
        for i in range(1, periods):
            if trend_type == 'uptrend':
                # Xu hướng tăng giá
                change = np.random.normal(0.002, self.volatility)
            elif trend_type == 'downtrend':
                # Xu hướng giảm giá
                change = np.random.normal(-0.002, self.volatility)
            elif trend_type == 'volatile':
                # Thị trường biến động mạnh
                change = np.random.normal(0, self.volatility * 2)
            else:
                # Thị trường đi ngang
                change = np.random.normal(0, self.volatility / 2)
                
            # Thêm một số đỉnh và đáy để tạo tín hiệu RSI rõ ràng
            if i % 20 == 0 and trend_type == 'volatile':
                if random.random() > 0.5:
                    # Đỉnh giá (có thể tạo tín hiệu short)
                    change = self.volatility * 3
                else:
                    # Đáy giá (có thể tạo tín hiệu long)
                    change = -self.volatility * 3
                    
            new_price = prices[-1] * (1 + change)
            prices.append(max(100, new_price))  # Giá tối thiểu là 100
            
        return prices
        
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Giả lập API fetch_ohlcv của Binance"""
        now = datetime.datetime.now()
        
        # Tính khoảng thời gian dựa trên timeframe
        if timeframe == '1h':
            delta = datetime.timedelta(hours=1)
        elif timeframe == '15m':
            delta = datetime.timedelta(minutes=15)
        elif timeframe == '1d':
            delta = datetime.timedelta(days=1)
        else:
            delta = datetime.timedelta(hours=1)  # Mặc định 1h
            
        # Tạo giá mock
        prices = self._generate_mock_price(limit)
        
        # Tạo dữ liệu OHLCV
        ohlcv_data = []
        for i in range(limit):
            timestamp = int((now - delta * (limit - i - 1)).timestamp() * 1000)
            price = prices[i]
            
            # Tạo giá O, H, L dựa trên giá đóng cửa
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
        self.alert_cooldown = 3600  # 1 giờ cooldown giữa các cảnh báo
        self.current_position = None  # None = không có vị thế, 'long' = đang long, 'short' = đang short
        self.mock_speed = 60  # Tốc độ chạy nhanh hơn 5 lần khi dùng mock
        
        # Thêm các biến để tính PnL
        self.position_size = 100  # USD
        self.leverage = 20
        self.entry_price = None
        self.entry_time = None
        self.total_pnl = 0  # Tổng PnL tích lũy
        self.trade_count = 0  # Số lượng giao dịch đã thực hiện
        self.winning_trades = 0  # Số giao dịch thắng
        
        # Thêm biến để lưu message ID
        self.entry_message_id = None  # Lưu message ID khi mở lệnh
        
        # Cấu hình signal mode
        self.signal_mode = SIGNAL_MODE
        self.rsi_independent = RSI_INDEPENDENT
        self.macd_independent = MACD_INDEPENDENT
        
    def _init_exchange(self):
        """Khởi tạo kết nối với sàn Binance hoặc mock Binance"""
        try:
            if self.use_mock:
                logger.info("Sử dụng dữ liệu mock cho việc test")
                return MockBinance(starting_price=20000, volatility=0.05, timeframe=RSI_TIMEFRAME)
            else:
                exchange = ccxt.binance({
                    'apiKey': BINANCE_API_KEY,
                    'secret': BINANCE_SECRET_KEY,
                    'enableRateLimit': True,
                })
                logger.info(f"Đã kết nối thành công tới Binance")
                return exchange
        except Exception as e:
            logger.error(f"Lỗi kết nối tới Binance: {e}")
            raise
            
    def _init_telegram_bot(self):
        """Khởi tạo bot Telegram với hỗ trợ proxy"""
        try:
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                logger.warning("Thiếu thông tin TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong biến môi trường.")
                raise ValueError("Thiếu thông tin cấu hình Telegram")
            
            # Tạo request với proxy nếu có
            if TELEGRAM_PROXY_URL:
                request = HTTPXRequest(proxy=TELEGRAM_PROXY_URL)
                bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN, request=request)
                logger.info(f"Đã kết nối thành công tới Telegram bot với proxy: {TELEGRAM_PROXY_URL}, Chat ID: {TELEGRAM_CHAT_ID}")
            else:
                bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
                logger.info(f"Đã kết nối thành công tới Telegram bot (không sử dụng proxy), Chat ID: {TELEGRAM_CHAT_ID}")
            
            return bot
        except Exception as e:
            logger.error(f"Lỗi kết nối tới Telegram: {e}")
            raise
    
    def fetch_ohlcv_data(self, timeframe=RSI_TIMEFRAME, limit=100):
        """Lấy dữ liệu giá từ Binance"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu OHLCV cho {self.symbol}: {e}")
            return None
    
    def calculate_rsi(self, df, window=RSI_WINDOW):
        """Tính toán chỉ báo RSI từ dữ liệu giá"""
        if df is None or len(df) < window:
            return None
            
        try:
            rsi_indicator = RSIIndicator(close=df['close'], window=window)
            df['rsi'] = rsi_indicator.rsi()
            return df
        except Exception as e:
            logger.error(f"Lỗi khi tính toán RSI: {e}")
            return None
    
    def calculate_macd(self, df, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
        """Tính toán chỉ báo MACD từ dữ liệu giá"""
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
            logger.error(f"Lỗi khi tính toán MACD: {e}")
            return None
    
    def calculate_pnl(self, entry_price, exit_price, position_type):
        """Tính toán PnL với đòn bẩy x20"""
        if entry_price is None or exit_price is None:
            return 0
            
        # Tính phần trăm thay đổi giá
        if position_type == 'long':
            price_change_percent = (exit_price - entry_price) / entry_price
        elif position_type == 'short':
            price_change_percent = (entry_price - exit_price) / entry_price
        else:
            return 0
            
        # Áp dụng đòn bẩy
        leveraged_return = price_change_percent * self.leverage
        
        # Tính PnL bằng USD
        pnl_usd = self.position_size * leveraged_return
        
        return pnl_usd
    
    def get_current_pnl(self, current_price):
        """Tính PnL hiện tại của vị thế đang mở"""
        if self.entry_price is None or self.current_position not in ['long', 'short']:
            return 0
            
        return self.calculate_pnl(self.entry_price, current_price, self.current_position)
    
    def check_rsi_signal(self, df):
        """Kiểm tra tín hiệu RSI độc lập"""
        if df is None or 'rsi' not in df.columns:
            return None
            
        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        
        if np.isnan(latest_rsi):
            return None
            
        current_time = time.time()
        cooldown_time = self.alert_cooldown/self.mock_speed if self.use_mock else self.alert_cooldown
        
        # RSI Long signal
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
                
        # RSI Short signal  
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
        """Kiểm tra tín hiệu MACD độc lập"""
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
        cooldown_time = self.alert_cooldown/self.mock_speed if self.use_mock else self.alert_cooldown
        
        # MACD Bullish crossover
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
                
        # MACD Bearish crossover
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
        """Lấy trạng thái các signal khác để hiển thị tham khảo"""
        reference = {}
        
        if exclude_type != 'rsi' and 'rsi' in df.columns:
            latest_rsi = df['rsi'].iloc[-1]
            if not np.isnan(latest_rsi):
                if latest_rsi < RSI_OVERSOLD:
                    rsi_status = "Oversold (Tín hiệu Long)"
                elif latest_rsi > RSI_OVERBOUGHT:
                    rsi_status = "Overbought (Tín hiệu Short)"
                else:
                    rsi_status = "Neutral"
                reference['rsi'] = {'value': latest_rsi, 'status': rsi_status}
                
        if exclude_type != 'macd' and 'macd' in df.columns and len(df) >= 2:
            latest_macd = df['macd'].iloc[-1]
            latest_macd_signal = df['macd_signal'].iloc[-1]
            
            if not any(np.isnan([latest_macd, latest_macd_signal])):
                if latest_macd > latest_macd_signal:
                    macd_status = "Bullish (Xu hướng tăng)"
                else:
                    macd_status = "Bearish (Xu hướng giảm)"
                reference['macd'] = {
                    'macd': latest_macd,
                    'signal': latest_macd_signal,
                    'status': macd_status
                }
                
        return reference
    
    def check_entry_conditions(self, df):
        """Kiểm tra điều kiện vào lệnh với các signal độc lập"""
        if df is None:
            return None
            
        # Kiểm tra điều kiện thoát lệnh trước
        if self.current_position in ['long', 'short']:
            return self._check_exit_conditions(df)
            
        # Kiểm tra các tín hiệu vào lệnh mới
        signals_to_check = []
        
        if self.signal_mode in ['RSI', 'BOTH'] and self.rsi_independent:
            rsi_signal = self.check_rsi_signal(df)
            if rsi_signal:
                signals_to_check.append(rsi_signal)
                
        if self.signal_mode in ['MACD', 'BOTH'] and self.macd_independent:
            macd_signal = self.check_macd_signal(df)
            if macd_signal:
                signals_to_check.append(macd_signal)
                
        # Trả về signal đầu tiên được kích hoạt
        if signals_to_check:
            selected_signal = signals_to_check[0]  # Có thể thêm logic ưu tiên
            
            # Thêm thông tin tham khảo từ các signal khác
            reference_signals = self.get_reference_signals(df, exclude_type=selected_signal['signal_type'])
            selected_signal['reference_signals'] = reference_signals
            
            # Lưu thông tin entry
            self.entry_price = selected_signal['price']
            self.entry_time = time.time()
            self.last_alert_time = time.time()
            
            return selected_signal
            
        # Log thông tin chỉ báo hiện tại
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
                logger.info(f"Chỉ báo {self.symbol}: RSI: {latest_rsi:.2f}{macd_info}")
            
            # Nếu đang có vị thế, thêm thông tin PnL hiện tại
            if self.current_position in ['long', 'short'] and self.entry_price is not None:
                current_pnl = self.get_current_pnl(latest_close)
                logger.info(f"PnL hiện tại cho {self.symbol}: ${current_pnl:.2f}")
            
        return None

    def _check_exit_conditions(self, df):
        """Kiểm tra điều kiện thoát lệnh"""
        if df is None or 'rsi' not in df.columns:
            return None
            
        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        current_time = time.time()
        cooldown_time = self.alert_cooldown/self.mock_speed if self.use_mock else self.alert_cooldown
        
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
        """Gửi cảnh báo qua Telegram"""
        try:
            coin_name = self.symbol.split('/')[0]
            signal = signal_data['signal']
            rsi_value = signal_data['rsi']
            price = signal_data['price']
            
            # Lấy signal logger
            signal_logger = logging.getLogger('trading_signals')
            
            # Tách chat_id và message_thread_id nếu có
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
                    message = (f"🚨 TÍN HIỆU LONG (RSI): {coin_name} tại giá ${price:.2f}\n"
                              f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_OVERSOLD} → Bị bán quá mức (oversold)\n")
                    
                elif signal_type == 'macd':
                    macd = signal_data['macd']
                    macd_signal_val = signal_data['macd_signal']
                    macd_histogram = signal_data['macd_histogram']
                    message = (f"🚨 TÍN HIỆU LONG (MACD): {coin_name} tại giá ${price:.2f}\n"
                              f"📈 MACD ({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) = {macd:.4f} cắt lên {macd_signal_val:.4f} → Tín hiệu tăng\n"
                              f"📊 Histogram = {macd_histogram:.4f}\n")
                else:
                    # Fallback for old format
                    rsi_value = signal_data.get('rsi', 0)
                    message = (f"🚨 TÍN HIỆU LONG: {coin_name} tại giá ${price:.2f}\n"
                              f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_OVERSOLD} → Bị bán quá mức (oversold)\n")
                
                # Thêm thông tin tham khảo
                if 'reference_signals' in signal_data:
                    ref = signal_data['reference_signals']
                    if 'rsi' in ref and signal_type != 'rsi':
                        message += f"📊 RSI tham khảo: {ref['rsi']['value']:.2f} - {ref['rsi']['status']}\n"
                    if 'macd' in ref and signal_type != 'macd':
                        message += f"📈 MACD tham khảo: {ref['macd']['macd']:.4f} - {ref['macd']['status']}\n"
                        
                message += (f"👉 Khuyến nghị: MUA VÀO (LONG)\n"
                           f"💰 Vị thế: ${position_size} với đòn bẩy x{leverage}\n"
                           f"🔄 Thoát lệnh khi RSI > {RSI_EXIT}")
                           
                self.current_position = 'long'
                
                # Log signal
                signal_logger.info(f"LONG_ENTRY_{signal_type.upper()} | {coin_name} | Price: ${price:.2f} | Trigger: {trigger} | Size: ${position_size} | Leverage: x{leverage}")
                
                # Gửi tin nhắn và lưu message ID
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
                
                # Lưu message ID để reply sau này
                self.entry_message_id = sent_message.message_id
                
            elif signal == 'short':
                signal_type = signal_data.get('signal_type', 'combined')
                trigger = signal_data.get('trigger', '')
                position_size = signal_data['position_size']
                leverage = signal_data['leverage']
                
                if signal_type == 'rsi':
                    rsi_value = signal_data['rsi']
                    message = (f"🚨 TÍN HIỆU SHORT (RSI): {coin_name} tại giá ${price:.2f}\n"
                              f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_OVERBOUGHT} → Bị mua quá mức (overbought)\n")
                              
                elif signal_type == 'macd':
                    macd = signal_data['macd']
                    macd_signal_val = signal_data['macd_signal']
                    macd_histogram = signal_data['macd_histogram']
                    message = (f"🚨 TÍN HIỆU SHORT (MACD): {coin_name} tại giá ${price:.2f}\n"
                              f"📉 MACD ({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) = {macd:.4f} cắt xuống {macd_signal_val:.4f} → Tín hiệu giảm\n"
                              f"📊 Histogram = {macd_histogram:.4f}\n")
                else:
                    # Fallback for old format
                    rsi_value = signal_data.get('rsi', 0)
                    message = (f"🚨 TÍN HIỆU SHORT: {coin_name} tại giá ${price:.2f}\n"
                              f"📊 RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_OVERBOUGHT} → Bị mua quá mức (overbought)\n")
                
                # Thêm thông tin tham khảo
                if 'reference_signals' in signal_data:
                    ref = signal_data['reference_signals']
                    if 'rsi' in ref and signal_type != 'rsi':
                        message += f"📊 RSI tham khảo: {ref['rsi']['value']:.2f} - {ref['rsi']['status']}\n"
                    if 'macd' in ref and signal_type != 'macd':
                        message += f"📉 MACD tham khảo: {ref['macd']['macd']:.4f} - {ref['macd']['status']}\n"
                        
                message += (f"👉 Khuyến nghị: BÁN KHỐNG (SHORT)\n"
                           f"💰 Vị thế: ${position_size} với đòn bẩy x{leverage}\n"
                           f"🔄 Thoát lệnh khi RSI < {RSI_EXIT}")
                           
                self.current_position = 'short'
                
                # Log signal
                signal_logger.info(f"SHORT_ENTRY_{signal_type.upper()} | {coin_name} | Price: ${price:.2f} | Trigger: {trigger} | Size: ${position_size} | Leverage: x{leverage}")
                
                # Gửi tin nhắn và lưu message ID
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
                
                # Lưu message ID để reply sau này
                self.entry_message_id = sent_message.message_id
                
            elif signal == 'exit_long':
                entry_price = signal_data['entry_price']
                pnl = signal_data['pnl']
                total_pnl = signal_data['total_pnl']
                trade_count = signal_data['trade_count']
                win_rate = signal_data['win_rate']
                
                pnl_emoji = "💚" if pnl > 0 else "❤️"
                price_change = ((price - entry_price) / entry_price) * 100
                
                message = (f"🔔 TÍN HIỆU THOÁT LONG: {coin_name}\n"
                          f"📈 Giá vào: ${entry_price:.2f} → Giá ra: ${price:.2f}\n"
                          f"📊 Thay đổi giá: {price_change:+.2f}%\n"
                          f"RSI ({RSI_WINDOW}) = {rsi_value:.2f} > {RSI_EXIT}\n"
                          f"👉 Khuyến nghị: ĐÓNG VỊ THẾ LONG\n"
                          f"{pnl_emoji} PnL giao dịch này: ${pnl:+.2f}\n"
                          f"💰 Tổng PnL: ${total_pnl:+.2f}\n"
                          f"📈 Số giao dịch: {trade_count} | Tỷ lệ thắng: {win_rate:.1f}%")
                self.current_position = 'exit_long'
                
                # Log signal vào file riêng
                signal_logger.info(f"LONG_EXIT | {coin_name} | Entry: ${entry_price:.2f} | Exit: ${price:.2f} | PnL: ${pnl:+.2f} | Total_PnL: ${total_pnl:+.2f} | Win_Rate: {win_rate:.1f}%")
                
                # Reply vào message mở lệnh nếu có
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
                    # Nếu không có message ID thì gửi bình thường
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
                
                # Reset entry price và message ID sau khi đóng lệnh
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
                
                message = (f"🔔 TÍN HIỆU THOÁT SHORT: {coin_name}\n"
                          f"📉 Giá vào: ${entry_price:.2f} → Giá ra: ${price:.2f}\n"
                          f"📊 Thay đổi giá: {price_change:+.2f}% (cho short)\n"
                          f"RSI ({RSI_WINDOW}) = {rsi_value:.2f} < {RSI_EXIT}\n"
                          f"👉 Khuyến nghị: ĐÓNG VỊ THẾ SHORT\n"
                          f"{pnl_emoji} PnL giao dịch này: ${pnl:+.2f}\n"
                          f"💰 Tổng PnL: ${total_pnl:+.2f}\n"
                          f"📈 Số giao dịch: {trade_count} | Tỷ lệ thắng: {win_rate:.1f}%")
                self.current_position = 'exit_short'
                
                # Log signal vào file riêng
                signal_logger.info(f"SHORT_EXIT | {coin_name} | Entry: ${entry_price:.2f} | Exit: ${price:.2f} | PnL: ${pnl:+.2f} | Total_PnL: ${total_pnl:+.2f} | Win_Rate: {win_rate:.1f}%")
                
                # Reply vào message mở lệnh nếu có
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
                    # Nếu không có message ID thì gửi bình thường
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
                
                # Reset entry price và message ID sau khi đóng lệnh
                self.entry_price = None
                self.entry_time = None
                self.entry_message_id = None
            
            logger.info(f"Đã gửi cảnh báo {signal} tới Telegram cho {self.symbol}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi gửi cảnh báo tới Telegram cho {self.symbol}: {e}")
            return False
            
    async def run(self):
        """Chạy bot"""
        logger.info(f"Bắt đầu chạy bot giám sát RSI + MACD cho {self.symbol} với chiến lược Long/Short")
        logger.info(f"Chiến lược RSI: Long khi RSI < {RSI_OVERSOLD}, Short khi RSI > {RSI_OVERBOUGHT}, Thoát lệnh khi RSI = {RSI_EXIT}")
        logger.info(f"Chiến lược MACD: Kết hợp với tín hiệu MACD crossover và divergence (Tham số: {MACD_FAST},{MACD_SLOW},{MACD_SIGNAL})")
        logger.info(f"Cấu hình giao dịch: Vị thế ${self.position_size} với đòn bẩy x{self.leverage}")
        
        # Lấy thông tin chat khi khởi động bot
        await self.get_chat_info()
        
        try:
            while True:
                # Lấy dữ liệu
                df = self.fetch_ohlcv_data()
                
                # Tính RSI
                df = self.calculate_rsi(df)
                
                # Tính MACD
                df = self.calculate_macd(df)
                
                # Kiểm tra điều kiện
                signal_data = self.check_entry_conditions(df)
                if signal_data:
                    await self.send_telegram_alert(signal_data)
                
                # Hiển thị thống kê giao dịch định kỳ
                if self.trade_count > 0:
                    win_rate = (self.winning_trades / self.trade_count) * 100
                    logger.info(f"📊 Thống kê {self.symbol}: {self.trade_count} giao dịch | "
                              f"Tỷ lệ thắng: {win_rate:.1f}% | Tổng PnL: ${self.total_pnl:+.2f}")
                
                # Chờ thời gian trước khi kiểm tra lại (5 phút thực tế hoặc nhanh hơn khi dùng mock)
                sleep_time = 300 / self.mock_speed if self.use_mock else 300
                logger.info(f"Đợi {sleep_time:.1f} giây trước khi kiểm tra lại {self.symbol}...")
                await asyncio.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info(f"Bot cho {self.symbol} đã dừng bởi người dùng")
            # Hiển thị thống kê cuối cùng
            if self.trade_count > 0:
                win_rate = (self.winning_trades / self.trade_count) * 100
                logger.info(f"📊 Thống kê cuối cùng {self.symbol}: {self.trade_count} giao dịch | "
                          f"Tỷ lệ thắng: {win_rate:.1f}% | Tổng PnL: ${self.total_pnl:+.2f}")
        except Exception as e:
            logger.error(f"Lỗi không xử lý được cho {self.symbol}: {e}")

    def get_trading_stats(self):
        """Lấy thống kê giao dịch"""
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
        """Lấy và log thông tin chi tiết của chat"""
        try:
            # Tách chat_id và message_thread_id nếu có
            if '_' in TELEGRAM_CHAT_ID:
                chat_id, message_thread_id = TELEGRAM_CHAT_ID.split('_')
                chat_id = int(chat_id)
                message_thread_id = int(message_thread_id)
            else:
                chat_id = int(TELEGRAM_CHAT_ID)
                message_thread_id = None
            
            # Lấy thông tin chat
            chat_info = await self.bot.get_chat(chat_id)
            
            # Log thông tin chi tiết
            logger.info(f"📋 Thông tin Chat:")
            logger.info(f"   - ID: {chat_info.id}")
            logger.info(f"   - Type: {chat_info.type}")
            
            if chat_info.title:
                logger.info(f"   - Title: {chat_info.title}")
            if chat_info.username:
                logger.info(f"   - Username: @{chat_info.username}")
            if chat_info.first_name:
                logger.info(f"   - First Name: {chat_info.first_name}")
            if chat_info.last_name:
                logger.info(f"   - Last Name: {chat_info.last_name}")
            if chat_info.description:
                logger.info(f"   - Description: {chat_info.description}")
            
            if message_thread_id:
                logger.info(f"   - Message Thread ID: {message_thread_id}")
                
            # Kiểm tra quyền bot trong group/channel
            if chat_info.type in ['group', 'supergroup', 'channel']:
                try:
                    bot_member = await self.bot.get_chat_member(chat_id, self.bot.id)
                    logger.info(f"   - Bot Status: {bot_member.status}")
                    if hasattr(bot_member, 'can_post_messages'):
                        logger.info(f"   - Can Post Messages: {bot_member.can_post_messages}")
                except Exception as e:
                    logger.warning(f"   - Không thể lấy thông tin quyền bot: {e}")
            
        except Exception as e:
            logger.warning(f"Không thể lấy thông tin chi tiết của chat {TELEGRAM_CHAT_ID}: {e}")

class MultiPairSignalBot:
    def __init__(self, trading_pairs, use_mock=False):
        self.trading_pairs = trading_pairs
        self.use_mock = use_mock
        self.bots = {}
        self._init_bots()

    def _init_bots(self):
        """Khởi tạo bot cho từng cặp giao dịch"""
        for pair in self.trading_pairs:
            self.bots[pair] = CryptoSignalBot(symbol=pair, use_mock=self.use_mock)
            logger.info(f"Đã khởi tạo bot cho {pair}")

    def get_combined_stats(self):
        """Lấy thống kê tổng hợp từ tất cả các bot"""
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
        """Hiển thị thống kê tổng hợp"""
        stats = self.get_combined_stats()
        
        logger.info("=" * 60)
        logger.info("📊 THỐNG KÊ TỔNG HỢP TẤT CẢ CÁC CẶP GIAO DỊCH")
        logger.info(f"💰 Tổng PnL: ${stats['total_pnl']:+.2f}")
        logger.info(f"📈 Tổng số giao dịch: {stats['total_trades']}")
        logger.info(f"🎯 Tỷ lệ thắng tổng: {stats['overall_win_rate']:.1f}%")
        logger.info(f"🔄 Vị thế đang mở: {stats['active_positions']}")
        
        logger.info("\n📋 Chi tiết theo từng cặp:")
        for pair, pair_stats in stats['stats_by_pair'].items():
            status = ""
            if pair_stats['current_position'] in ['long', 'short']:
                status = f" (Đang {pair_stats['current_position'].upper()} tại ${pair_stats['entry_price']:.2f})"
            
            logger.info(f"  {pair}: {pair_stats['total_trades']} giao dịch | "
                       f"Thắng {pair_stats['win_rate']:.1f}% | "
                       f"PnL: ${pair_stats['total_pnl']:+.2f}{status}")
        logger.info("=" * 60)

    async def run_all(self):
        """Chạy tất cả các bot đồng thời"""
        try:
            # Tạo danh sách các coroutine để chạy
            tasks = [bot.run() for bot in self.bots.values()]
            # Chạy tất cả các bot cùng lúc
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Tất cả bot đã dừng bởi người dùng")
            # Hiển thị thống kê cuối cùng
            self.log_combined_stats()
        except Exception as e:
            logger.error(f"Lỗi khi chạy đa bot: {e}")
            self.log_combined_stats()

if __name__ == "__main__":
    # Thêm các tham số để chọn chế độ thực/mock
    parser = argparse.ArgumentParser(description='Crypto Signal Bot với chiến lược Long/Short dựa trên RSI')
    parser.add_argument('--mock', action='store_true', help='Chạy với dữ liệu mock để test')
    args = parser.parse_args()
    
    # Log thông tin khởi động
    logger.info("=" * 80)
    logger.info("🚀 KHỞI ĐỘNG CRYPTO SIGNAL BOT")
    logger.info("=" * 80)
    logger.info(f"📁 Log files được lưu tại:")
    logger.info(f"   - Tổng quát: logs/crypto_signal_bot.log")
    logger.info(f"   - Trading signals: logs/trading_signals.log")
    logger.info(f"🔧 Chế độ: {'Mock (Test)' if args.mock else 'Live Trading'}")
    logger.info(f"🎯 Signal Mode: {SIGNAL_MODE} | RSI Independent: {RSI_INDEPENDENT} | MACD Independent: {MACD_INDEPENDENT}")
    logger.info(f"📊 Cặp giao dịch: {', '.join(TRADING_PAIRS)}")
    logger.info(f"⚙️  Cấu hình RSI: Window={RSI_WINDOW}, Timeframe={RSI_TIMEFRAME}")
    logger.info(f"📈 Ngưỡng RSI: Oversold<{RSI_OVERSOLD}, Overbought>{RSI_OVERBOUGHT}, Exit={RSI_EXIT}")
    logger.info(f"📊 Cấu hình MACD: Fast={MACD_FAST}, Slow={MACD_SLOW}, Signal={MACD_SIGNAL}")
    logger.info("=" * 80)
    
    # Log signal khởi động vào file trading signals
    signal_logger = logging.getLogger('trading_signals')
    signal_logger.info(f"BOT_START | Mode: {'Mock' if args.mock else 'Live'} | Pairs: {','.join(TRADING_PAIRS)} | RSI_Config: {RSI_WINDOW}_{RSI_TIMEFRAME}_{RSI_OVERSOLD}_{RSI_OVERBOUGHT}_{RSI_EXIT} | MACD_Config: {MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}")
    
    try:
        multi_bot = MultiPairSignalBot(trading_pairs=TRADING_PAIRS, use_mock=args.mock)
        asyncio.run(multi_bot.run_all())
    except Exception as e:
        logger.error(f"Lỗi khởi động bot: {e}")
        signal_logger.info(f"BOT_ERROR | Error: {str(e)}")
    finally:
        logger.info("🛑 Bot đã dừng hoàn toàn")
        signal_logger.info("BOT_STOP | Bot stopped") 