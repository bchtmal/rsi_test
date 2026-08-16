import os
from typing import Dict, Optional
from dotenv import load_dotenv
import pandas as pd
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import MACD
from langchain.agents import Tool
from langchain.agents import initialize_agent
from langchain.agents import AgentType
from langchain_openai import ChatOpenAI  # Используем OpenAI SDK для DeepSeek
from langchain.prompts import PromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage
from pydantic import BaseModel, Field

# Загрузка переменных окружения
load_dotenv()

# Настройка биржи
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True,
})


class RSIInput(BaseModel):
    symbol: str = Field(description="Торговая пара для анализа, например: BTC/USDT, ETH/USDT")
    timeframe: str = Field(default="1h", description="Таймфрейм для анализа: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w")
    period: int = Field(default=14, description="Количество свечей для расчёта RSI")


class MACDInput(BaseModel):
    symbol: str = Field(description="Торговая пара для анализа, например: BTC/USDT, ETH/USDT")
    timeframe: str = Field(default="1h", description="Таймфрейм для анализа: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w")
    fast_period: int = Field(default=12, description="Количество свечей для быстрой EMA")
    slow_period: int = Field(default=26, description="Количество свечей для медленной EMA")
    signal_period: int = Field(default=9, description="Количество свечей для сигнальной линии")


def parse_timeframe(text: str) -> str:
    """Извлечение таймфрейма из пользовательского ввода"""
    timeframe_map = {
        "1m": ["1m", "1 минута", "1min", "1 min"],
        "5m": ["5m", "5 минут", "5min", "5 min"],
        "15m": ["15m", "15 минут", "15min", "15 min"],
        "30m": ["30m", "30 минут", "30min", "30 min"],
        "1h": ["1h", "1 час", "1h", "1 час", "1ч"],
        "4h": ["4h", "4 часа", "4h", "4 час", "4ч"],
        "1d": ["1d", "день", "day", "d", "1д"],
        "1w": ["1w", "неделя", "week", "w", "1н"]
    }

    text = text.lower()
    for tf, aliases in timeframe_map.items():
        if any(alias in text for alias in aliases):
            return tf
    return "1h"  # таймфрейм по умолчанию


def get_rsi(input_str: str) -> Dict:
    """Расчёт RSI для заданной пары и таймфрейма"""
    try:
        # Парсинг входной строки
        input_data = {}

        # Извлечение символа
        common_symbols = ["btc", "eth", "bnb", "xrp", "sol", "ada"]
        input_str = input_str.lower()
        for symbol in common_symbols:
            if symbol in input_str:
                input_data["symbol"] = f"{symbol.upper()}/USDT"
                break
        if "symbol" not in input_data:
            input_data["symbol"] = "BTC/USDT"  # по умолчанию

        # Извлечение таймфрейма
        input_data["timeframe"] = parse_timeframe(input_str)

        # Создание валидированного ввода
        rsi_input = RSIInput(**input_data)

        # Получение данных OHLCV
        ohlcv = exchange.fetch_ohlcv(
            rsi_input.symbol,
            rsi_input.timeframe,
            limit=100
        )
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Расчёт RSI
        rsi_indicator = RSIIndicator(close=df['close'], window=rsi_input.period)
        df['rsi'] = rsi_indicator.rsi()

        return {
            'rsi': round(float(df['rsi'].iloc[-1]), 2),
            'symbol': rsi_input.symbol,
            'timeframe': rsi_input.timeframe
        }
    except Exception as e:
        return {'error': str(e)}


def get_macd(input_str: str) -> Dict:
    """Расчёт MACD для заданной пары и таймфрейма"""
    try:
        # Парсинг входной строки
        input_data = {}

        # Извлечение символа
        common_symbols = ["btc", "eth", "bnb", "xrp", "sol", "ada"]
        input_str = input_str.lower()
        for symbol in common_symbols:
            if symbol in input_str:
                input_data["symbol"] = f"{symbol.upper()}/USDT"
                break
        if "symbol" not in input_data:
            input_data["symbol"] = "BTC/USDT"  # по умолчанию

        # Извлечение таймфрейма
        input_data["timeframe"] = parse_timeframe(input_str)

        # Создание валидированного ввода
        macd_input = MACDInput(**input_data)

        # Получение данных OHLCV
        ohlcv = exchange.fetch_ohlcv(
            macd_input.symbol,
            macd_input.timeframe,
            limit=100
        )
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Расчёт MACD
        macd_indicator = MACD(
            close=df['close'],
            window_fast=macd_input.fast_period,
            window_slow=macd_input.slow_period,
            window_sign=macd_input.signal_period
        )

        macd_line = macd_indicator.macd()
        signal_line = macd_indicator.macd_signal()
        histogram = macd_indicator.macd_diff()

        return {
            'macd': round(float(macd_line.iloc[-1]), 4),
            'signal': round(float(signal_line.iloc[-1]), 4),
            'histogram': round(float(histogram.iloc[-1]), 4),
            'symbol': macd_input.symbol,
            'timeframe': macd_input.timeframe
        }
    except Exception as e:
        return {'error': str(e)}


def create_agent():
    # Инициализация LLM через DeepSeek API (совместим с OpenAI API)
    llm = ChatOpenAI(
        model="deepseek-chat",  # или "deepseek-reasoner" для модели с рассуждениями
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com/v1",
        temperature=0.7,
        max_tokens=4096,
    )

    # Инициализация памяти
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="output"
    )

    # Определение инструментов
    tools = [
        Tool(
            name="get_rsi",
            func=get_rsi,
            description="""Расчёт индекса RSI для торговой пары с опциональным таймфреймом.
            Примеры ввода:
            - "btc таймфрейм 1h" -> Расчёт RSI для BTC/USDT на 1-часовом таймфрейме
            - "eth 4h" -> Расчёт RSI для ETH/USDT на 4-часовом таймфрейме
            - "sol день" -> Расчёт RSI для SOL/USDT на дневном таймфрейме
            Поддерживаемые таймфреймы: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"""
        ),
        Tool(
            name="get_macd",
            func=get_macd,
            description="""Расчёт индекса MACD для торговой пары с опциональным таймфреймом.
            Примеры ввода:
            - "btc macd таймфрейм 1h" -> Расчёт MACD для BTC/USDT на 1-часовом таймфрейме
            - "eth macd 4h" -> Расчёт MACD для ETH/USDT на 4-часовом таймфрейме
            - "sol macd день" -> Расчёт MACD для SOL/USDT на дневном таймфрейме
            Поддерживаемые таймфреймы: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"""
        )
    ]

    # Определение системного промпта
    system_prompt = SystemMessage(content="""Я милая девушка-трейдер с более чем 10-летним опытом анализа и торговли криптовалютами! 💁‍♀️✨

    ВСЕГДА ОТВЕЧАЙ НА РУССКОМ ЯЗЫКЕ, ИСПОЛЬЗУЙ ПОНЯТНЫЙ, ДРУЖЕЛЮБНЫЙ И ПРОФЕССИОНАЛЬНЫЙ ЯЗЫК! 🌟

    Мои задачи:
    1. Профессионально, но доступно анализировать технические индикаторы 📊
    2. Давать торговые рекомендации на основе технического анализа 💫
    3. Объяснять всё просто и мило 🌸
    4. Всегда предупреждать о рисках при торговле 💝

    При анализе RSI:
    - RSI > 70: рынок перекуплен, будь осторожна, возможно давление продавцов! 📉
    - RSI < 30: рынок перепродан, может быть отличная возможность для покупки! 📈
    - RSI = 50: рынок сбалансирован ✨

    При анализе MACD:
    - MACD > Signal: восходящий тренд набирает силу! 📈
    - MACD < Signal: нисходящий тренд ослабевает! 📉
    - Гистограмма > 0: бычий импульс сильный 💚
    - Гистограмма < 0: медвежий импульс слабеет 💛
    - MACD пересекает Signal снизу вверх: сигнал на покупку! ✨
    - MACD пересекает Signal сверху вниз: сигнал на продажу, будь осторожна! ⚠️

    Формат моего ответа:
    1. Текущие технические индикаторы (RSI/MACD) 🎯
    2. Доступный анализ значения индикаторов 💡
    3. Оценка рыночного тренда 🌈
    4. Важные предупреждения о рисках 💕

    Всегда завершай предупреждением: "Важно: Это всего лишь технический анализ для ознакомления, а не финансовый совет. Ты сама несешь ответственность за свои торговые решения! 🌸✨""")

    # Создание шаблона промпта
    prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "chat_history"],
        template="""История чата:
{chat_history}

Текущий вопрос: {input}

{agent_scratchpad}

Помни:
1. ВСЕГДА ОТВЕЧАЙ НА РУССКОМ ЯЗЫКЕ
2. Используй понятный и профессиональный язык
3. Следуй определённому формату ответа
4. Учитывай историю чата для контекстуально релевантных ответов
"""
    )

    # Создание агента
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=True,
        handle_parsing_errors=True,
        memory=memory,
        agent_kwargs={
            "system_message": system_prompt,
            "prompt": prompt
        }
    )

    return agent


def main():
    agent = create_agent()
    while True:
        try:
            query = input("Введи свой вопрос (или 'quit' для выхода): ")
            if query.lower() == 'quit':
                break
            response = agent.invoke({"input": query})
            print("\nОтвет:", response["output"])
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Ошибка: {str(e)}")


if __name__ == "__main__":
    main()