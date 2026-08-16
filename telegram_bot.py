import os
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from crypto_agent import create_agent

# Загрузка переменных окружения
load_dotenv()

# Инициализация крипто-агента
crypto_agent = create_agent()


def get_proxy_config():
    """Получение конфигурации прокси из переменных окружения."""
    proxy_url = os.getenv("PROXY_URL")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")

    if not proxy_url:
        return None

    # Формирование URL прокси с аутентификацией, если она предоставлена
    if proxy_username and proxy_password:
        # Разбор URL прокси для вставки учётных данных
        if "://" in proxy_url:
            protocol, rest = proxy_url.split("://", 1)
            proxy_url = f"{protocol}://{proxy_username}:{proxy_password}@{rest}"

    return proxy_url


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка приветственного сообщения при вводе команды /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет {user.mention_html()} 👋\n"
        "Я могу помочь тебе с анализом крипторынка.\n"
        f"Например: @{context.bot.username} анализ BTC/USDT"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка сообщений, в которых упоминается бот."""
    message = update.message.text
    bot_username = context.bot.username

    # Проверка, упоминается ли бот в сообщении
    if f"@{bot_username}" in message:
        # Удаление упоминания бота из сообщения
        query = message.replace(f"@{bot_username}", "").strip()

        # Отправка сообщения о начале обработки
        processing_msg = await update.message.reply_text(
            "⏳ Идёт анализ..."
        )

        try:
            # Получение ответа от крипто-агента
            response = crypto_agent.run(query)
            # Обновление сообщения с результатами
            await processing_msg.edit_text(response)
        except Exception as e:
            # Обновление сообщения с ошибкой
            await processing_msg.edit_text(
                "❌ Произошла ошибка. Пожалуйста, попробуй позже."
            )


def main() -> None:
    """Запуск бота."""
    # Получение конфигурации прокси
    proxy_url = get_proxy_config()

    # Создание приложения с поддержкой прокси
    builder = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN"))

    if proxy_url:
        # Настройка с прокси - передача строки URL напрямую
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
        print(f"🌐 Используется прокси: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")
    else:
        print("🔗 Прямое подключение (без прокси)")

    application = builder.build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запускается...")

    # Запуск бота до нажатия Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()