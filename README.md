# Crypto Signal Bot

Bot giám sát và cảnh báo tín hiệu giao dịch tiền điện tử qua Telegram. Bot hỗ trợ phân tích kỹ thuật kết hợp RSI và MACD để đưa ra tín hiệu giao dịch chính xác hơn.

## Tính năng

- Kết nối Binance qua CCXT để lấy dữ liệu giá theo thời gian thực
- Tính toán chỉ báo RSI và MACD sử dụng thư viện TA
- Chiến lược giao dịch kết hợp RSI + MACD:
  - **Long**: RSI < 30 (oversold) + MACD bullish (MACD > Signal hoặc có bullish crossover)
  - **Short**: RSI > 70 (overbought) + MACD bearish (MACD < Signal hoặc có bearish crossover)
  - **Exit**: RSI về mức 50 (neutral)
- Gửi cảnh báo chi tiết qua Telegram với thông tin RSI và MACD
- Hỗ trợ nhiều cặp tiền đồng thời
- Tính toán PnL và thống kê giao dịch
- Có thể tùy chỉnh tất cả các thông số kỹ thuật

## Yêu cầu

- Python 3.8+
- Các thư viện trong file requirements.txt
- Tài khoản Binance (API key và Secret key)
- Bot Telegram đã được tạo

## Cài đặt

1. Clone repository:
```
git clone https://github.com/your-username/crypto-signal-bot.git
cd crypto-signal-bot
```

2. Cài đặt các thư viện yêu cầu:
```
pip install -r requirements.txt
```

3. Tạo file `.env` từ file mẫu:
```
cp .env-example .env
```

4. Cập nhật các thông tin trong file `.env` với API key của bạn:
```
# Binance API keys
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Bot settings - RSI
RSI_THRESHOLD=30
RSI_TIMEFRAME=1h
RSI_WINDOW=14
RSI_OVERSOLD=30
RSI_OVERBOUGHT=70
RSI_EXIT=50

# Bot settings - MACD
MACD_FAST=12
MACD_SLOW=26
MACD_SIGNAL=9

# Trading pairs
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT
COIN_SYMBOL=BTC/USDT

# Proxy settings (optional)
PROXY_URL=
PROXY_USERNAME=
PROXY_PASSWORD=
```

## Hướng dẫn tạo Telegram Bot

1. Mở Telegram và tìm kiếm `@BotFather`
2. Gửi lệnh `/newbot` và làm theo hướng dẫn
3. Sau khi tạo xong, bạn sẽ nhận được `TELEGRAM_BOT_TOKEN`
4. Để lấy `TELEGRAM_CHAT_ID`, tạo một nhóm chat, thêm bot vào nhóm, và sử dụng API để lấy chat ID

## Cấu hình Proxy (Tùy chọn)

Nếu bạn cần sử dụng proxy để kết nối Telegram, hãy cấu hình trong file `.env`:

```
PROXY_URL=http://proxy-server:8080
PROXY_USERNAME=your_username  # Nếu proxy yêu cầu authentication
PROXY_PASSWORD=your_password  # Nếu proxy yêu cầu authentication
```

Xem hướng dẫn chi tiết trong file [PROXY_GUIDE.md](PROXY_GUIDE.md).

### Test kết nối proxy

```
python test_proxy.py
```

## Chạy Bot

### Bot giám sát RSI + MACD (Trading Bot):
```
python main.py
```

### Bot Telegram chat (AI Assistant):
```
python crypto_agent.py
```

Bot trading sẽ tự động chạy và gửi cảnh báo qua Telegram khi có tín hiệu kết hợp từ RSI và MACD.

### Chạy với dữ liệu mock để test:
```
python main.py --mock
```

## Thêm cặp tiền khác

Bạn có thể thay đổi cặp tiền trong file `.env` bằng cách sửa biến `COIN_SYMBOL`, ví dụ:
```
COIN_SYMBOL=SOL/USDT
```

## Tùy chỉnh cảnh báo

### Cấu hình RSI:
```
RSI_WINDOW=14        # Số nến để tính RSI
RSI_OVERSOLD=30      # Ngưỡng quá bán (tín hiệu long)
RSI_OVERBOUGHT=70    # Ngưỡng quá mua (tín hiệu short)
RSI_EXIT=50          # Ngưỡng thoát lệnh
RSI_TIMEFRAME=4h     # Khung thời gian (1m, 5m, 15m, 1h, 4h, 1d)
```

### Cấu hình MACD:
```
MACD_FAST=12         # EMA nhanh
MACD_SLOW=26         # EMA chậm
MACD_SIGNAL=9        # EMA của đường Signal
```

### Cấu hình cặp giao dịch:
```
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT
```

## Đóng góp

Vui lòng gửi pull request hoặc báo lỗi qua Issues.

## License

MIT 