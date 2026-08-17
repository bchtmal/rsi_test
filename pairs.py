import ccxt

from main import BINANCE_API_KEY, BINANCE_SECRET_KEY


def get_all_futures_pairs():
    """Получение ВСЕХ USDT фьючерсных пар с Binance"""
    try:
        # Инициализация Binance Futures
        exchange = ccxt.binance({
            'apiKey': BINANCE_API_KEY,
            'secret': BINANCE_SECRET_KEY,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # КЛЮЧЕВОЙ ПАРАМЕТР!
                'adjustForTimeDifference': True,
            }
        })

        # Загрузка рынков
        exchange.load_markets()

        # Получаем все символы для фьючерсов
        all_pairs = []

        for symbol, market in exchange.markets.items():
            # Фильтр: только USDT фьючерсы, активные, линейные
            if (
                    market.get('settle') == 'USDT' and  # USDT-маржинированные
                    market.get('active', False) and  # Активные
                    market.get('linear', False) and  # Линейные (не инверсные)
                    '/USDT' in symbol and  # Заканчиваются на USDT
                    ':' not in symbol  # Не индексные фьючерсы
            ):
                all_pairs.append(symbol)

        # Сортируем для удобства
        all_pairs.sort()

        logger.info(f"✅ Найдено {len(all_pairs)} фьючерсных пар USDT")
        logger.info(f"📊 Первые 10 пар: {all_pairs[:10]}")

        return all_pairs

    except Exception as e:
        logger.error(f"❌ Ошибка получения списка пар: {e}")
        return []


# Использование
all_pairs = get_all_futures_pairs()
print(f"Всего пар: {len(all_pairs)}")