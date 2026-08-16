markdown
# Crypto Signal Bot

Бот для мониторинга и оповещения о торговых сигналах криптовалют через Telegram. Бот поддерживает технический анализ с комбинированным использованием RSI и MACD для выдачи более точных торговых сигналов.

## 📌 Возможности

- Подключение к Binance через библиотеку CCXT для получения данных о ценах в реальном времени
- Расчёт индикаторов RSI и MACD с использованием библиотеки TA
- Торговая стратегия, объединяющая RSI + MACD:
  - **Long (покупка)**: RSI < 30 (перепроданность) + бычий MACD (MACD > Signal или бычье пересечение)
  - **Short (продажа)**: RSI > 70 (перекупленность) + медвежий MACD (MACD < Signal или медвежье пересечение)
  - **Выход из позиции**: RSI достигает уровня 50 (нейтральный)
- Отправка детальных оповещений через Telegram с информацией о RSI и MACD
- Поддержка одновременного отслеживания нескольких торговых пар
- Расчёт PnL (прибыли/убытков) и статистики по сделкам
- Возможность настройки всех технических параметров

## ⚙️ Требования

- Python 3.8+
- Библиотеки из файла `requirements.txt`
- Аккаунт Binance (API-ключ и секретный ключ)
- Созданный Telegram-бот

## 🚀 Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/crypto-signal-bot.git
   cd crypto-signal-bot
Установите требуемые библиотеки:

bash
pip install -r requirements.txt
Создайте файл .env из примера:

bash
cp .env-example .env
Обновите информацию в файле .env, указав свои API-ключи:

env
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
🤖 Создание Telegram-бота
Откройте Telegram и найдите @BotFather

Отправьте команду /newbot и следуйте инструкциям

После создания вы получите TELEGRAM_BOT_TOKEN

Чтобы получить TELEGRAM_CHAT_ID, создайте групповой чат, добавьте туда бота и используйте API для получения ID чата

🌐 Настройка прокси (опционально)
Если для подключения к Telegram вам нужен прокси-сервер, настройте его в файле .env:

env
PROXY_URL=http://proxy-server:8080
PROXY_USERNAME=your_username  # Если прокси требует аутентификации
PROXY_PASSWORD=your_password  # Если прокси требует аутентификации
Подробная инструкция в файле PROXY_GUIDE.md.

Проверка подключения через прокси
bash
python test_proxy.py
▶️ Запуск бота
Торговый бот (мониторинг RSI + MACD):
bash
python main.py
Telegram-бот с ИИ-ассистентом (чат-бот):
bash
python crypto_agent.py
Торговый бот будет автоматически запущен и будет отправлять оповещения в Telegram при обнаружении комбинированных сигналов RSI и MACD.

Запуск с тестовыми (mock) данными:
bash
python main.py --mock
📊 Добавление других торговых пар
Вы можете изменить торговые пары в файле .env, отредактировав переменную COIN_SYMBOL, например:

env
COIN_SYMBOL=SOL/USDT
🔧 Настройка оповещений
Параметры RSI:
env
RSI_WINDOW=14        # Количество свечей для расчёта RSI
RSI_OVERSOLD=30      # Уровень перепроданности (сигнал на покупку)
RSI_OVERBOUGHT=70    # Уровень перекупленности (сигнал на продажу)
RSI_EXIT=50          # Уровень выхода из позиции
RSI_TIMEFRAME=4h     # Временной интервал (1m, 5m, 15m, 1h, 4h, 1d)
Параметры MACD:
env
MACD_FAST=12         # Быстрая EMA
MACD_SLOW=26         # Медленная EMA
MACD_SIGNAL=9        # EMA сигнальной линии
Список торговых пар:
env
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT
🤝 Вклад в проект
Пожалуйста, присылайте pull request или сообщайте об ошибках через раздел Issues.

📄 Лицензия
MIT