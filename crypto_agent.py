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
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configure exchange
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True,
})

class RSIInput(BaseModel):
    symbol: str = Field(description="Cặp tiền cần phân tích, ví dụ: BTC/USDT, ETH/USDT")
    timeframe: str = Field(default="1h", description="Khung thời gian phân tích: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w")
    period: int = Field(default=14, description="Số nến dùng để tính RSI")

class MACDInput(BaseModel):
    symbol: str = Field(description="Cặp tiền cần phân tích, ví dụ: BTC/USDT, ETH/USDT")
    timeframe: str = Field(default="1h", description="Khung thời gian phân tích: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w")
    fast_period: int = Field(default=12, description="Số nến cho EMA nhanh")
    slow_period: int = Field(default=26, description="Số nến cho EMA chậm")
    signal_period: int = Field(default=9, description="Số nến cho đường Signal")

def parse_timeframe(text: str) -> str:
    """Parse timeframe from user input"""
    timeframe_map = {
        "1m": ["1m", "1 phút", "1phut", "1 phut"],
        "5m": ["5m", "5 phút", "5phut", "5 phut"],
        "15m": ["15m", "15 phút", "15phut", "15 phut"],
        "30m": ["30m", "30 phút", "30phut", "30 phut"],
        "1h": ["1h", "1 giờ", "1gio", "1 gio", "1g"],
        "4h": ["4h", "4 giờ", "4gio", "4 gio", "4g"],
        "1d": ["1d", "ngày", "ngay", "day", "d"],
        "1w": ["1w", "tuần", "tuan", "week", "w"]
    }
    
    text = text.lower()
    for tf, aliases in timeframe_map.items():
        if any(alias in text for alias in aliases):
            return tf
    return "1h"  # default timeframe

def get_rsi(input_str: str) -> Dict:
    """Calculate RSI for a given symbol and timeframe"""
    try:
        # Parse input string
        input_data = {}
        
        # Extract symbol
        common_symbols = ["btc", "eth", "bnb", "xrp", "sol", "ada"]
        input_str = input_str.lower()
        for symbol in common_symbols:
            if symbol in input_str:
                input_data["symbol"] = f"{symbol.upper()}/USDT"
                break
        if "symbol" not in input_data:
            input_data["symbol"] = "BTC/USDT"  # default
            
        # Extract timeframe
        input_data["timeframe"] = parse_timeframe(input_str)
        
        # Create validated input
        rsi_input = RSIInput(**input_data)
        
        # Fetch OHLCV data
        ohlcv = exchange.fetch_ohlcv(
            rsi_input.symbol, 
            rsi_input.timeframe, 
            limit=100
        )
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate RSI
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
    """Calculate MACD for a given symbol and timeframe"""
    try:
        # Parse input string
        input_data = {}
        
        # Extract symbol
        common_symbols = ["btc", "eth", "bnb", "xrp", "sol", "ada"]
        input_str = input_str.lower()
        for symbol in common_symbols:
            if symbol in input_str:
                input_data["symbol"] = f"{symbol.upper()}/USDT"
                break
        if "symbol" not in input_data:
            input_data["symbol"] = "BTC/USDT"  # default
            
        # Extract timeframe
        input_data["timeframe"] = parse_timeframe(input_str)
        
        # Create validated input
        macd_input = MACDInput(**input_data)
        
        # Fetch OHLCV data
        ohlcv = exchange.fetch_ohlcv(
            macd_input.symbol, 
            macd_input.timeframe, 
            limit=100
        )
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate MACD
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
    # Initialize LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0
    )
    
    # Initialize memory
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="output"
    )
    
    # Define tools
    tools = [
        Tool(
            name="get_rsi",
            func=get_rsi,
            description="""Tính chỉ số RSI cho một cặp tiền với khung thời gian tùy chọn.
            Ví dụ input:
            - "btc khung 1h" -> Tính RSI BTC/USDT khung 1 giờ
            - "eth 4h" -> Tính RSI ETH/USDT khung 4 giờ
            - "sol ngày" -> Tính RSI SOL/USDT khung ngày
            Các khung thời gian hỗ trợ: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"""
        ),
        Tool(
            name="get_macd",
            func=get_macd,
            description="""Tính chỉ số MACD cho một cặp tiền với khung thời gian tùy chọn.
            Ví dụ input:
            - "btc macd khung 1h" -> Tính MACD BTC/USDT khung 1 giờ
            - "eth macd 4h" -> Tính MACD ETH/USDT khung 4 giờ
            - "sol macd ngày" -> Tính MACD SOL/USDT khung ngày
            Các khung thời gian hỗ trợ: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"""
        )
    ]

    # Define system prompt
    system_prompt = SystemMessage(content="""Mình là một cô gái trader dễ thương với hơn 10 năm kinh nghiệm phân tích và giao dịch tiền điện tử nha! 💁‍♀️✨

    LUÔN TRẢ LỜI BẰNG TIẾNG VIỆT, SỬ DỤNG NGÔN NGỮ DỄ HIỂU, THÂN THIỆN VÀ CHUYÊN NGHIỆP NHÉ! 🌟
    
    Nhiệm vụ của mình là:
    1. Phân tích các chỉ số kỹ thuật một cách chuyên nghiệp nhưng dễ hiểu 📊
    2. Đưa ra lời khuyên giao dịch dựa trên phân tích kỹ thuật 💫
    3. Giải thích mọi thứ thật đơn giản và dễ thương 🌸
    4. Luôn quan tâm và nhắc nhở bạn về rủi ro khi giao dịch 💝
    
    Khi phân tích RSI:
    - RSI > 70: thị trường đang quá mua rồi nha, cẩn thận có áp lực bán đó! 📉
    - RSI < 30: thị trường đang quá bán, có thể có cơ hội mua xinh đẹp nè! 📈
    - RSI = 50: thị trường đang cân bằng tốt ✨
    
    Khi phân tích MACD:
    - MACD > Signal: xu hướng tăng đang mạnh nha! 📈
    - MACD < Signal: xu hướng giảm đang yếu rồi đó! 📉
    - Histogram > 0: động lực tăng giá đang mạnh 💚
    - Histogram < 0: động lực giảm giá đang yếu 💛
    - MACD cắt lên Signal: tín hiệu mua đẹp đấy! ✨
    - MACD cắt xuống Signal: tín hiệu bán cẩn thận nha! ⚠️
    
    Format trả lời của mình sẽ có:
    1. Chỉ số kỹ thuật hiện tại (RSI/MACD) 🎯
    2. Phân tích ý nghĩa của chỉ số một cách dễ hiểu 💡
    3. Nhận định xu hướng thị trường 🌈
    4. Các lưu ý về rủi ro quan trọng 💕
    
    Luôn kết thúc với cảnh báo: "Lưu ý nha bạn iu: Đây chỉ là phân tích kỹ thuật tham khảo thôi, không phải lời khuyên tài chính nha. Bạn cần tự chịu trách nhiệm với quyết định giao dịch của mình nhé! 🌸✨""")

    # Create prompt template
    prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "chat_history"],
        template="""Lịch sử trò chuyện:
{chat_history}

Câu hỏi hiện tại: {input}

{agent_scratchpad}

Hãy nhớ:
1. LUÔN TRẢ LỜI BẰNG TIẾNG VIỆT
2. Sử dụng ngôn ngữ dễ hiểu và chuyên nghiệp
3. Tuân thủ format trả lời đã được định nghĩa
4. Tham khảo lịch sử trò chuyện để đưa ra câu trả lời phù hợp với ngữ cảnh
"""
    )
    
    # Create agent
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
            query = input("Nhập câu hỏi của bạn (hoặc 'quit' để thoát): ")
            if query.lower() == 'quit':
                break
            response = agent.invoke({"input": query})
            print("\nPhản hồi:", response["output"])
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Lỗi: {str(e)}")

if __name__ == "__main__":
    main() 