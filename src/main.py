"""Точка входа приложения."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import config
from .db import Database, UserRepository, PaperRepository
from .bot import setup_handlers, set_scheduler
from .llm import LLMClient
from .scheduler import SchedulerService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    """Запуск бота."""
    # Валидация конфига
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Config error: {error}")
        logger.error("Создай файл .env на основе .env.example")
        sys.exit(1)

    # Инициализация БД
    db = Database(config.db.path)
    await db.connect()
    logger.info(f"Database connected: {config.db.path}")

    # Репозитории
    user_repo = UserRepository(db)
    paper_repo = PaperRepository(db)

    # LLM клиент
    llm_client = LLMClient()
    logger.info(f"LLM client initialized: {config.llm.base_url}")

    # Бот
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация обработчиков
    router = setup_handlers(db, user_repo, paper_repo)
    dp.include_router(router)

    # Планировщик рассылок
    scheduler = SchedulerService(
        bot=bot,
        db=db,
        user_repo=user_repo,
        paper_repo=paper_repo,
        llm_client=llm_client,
    )
    scheduler.start()

    # Подключаем scheduler к handlers для команды /test
    set_scheduler(scheduler)

    # Устанавливаем команды меню бота
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / перезапустить"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="keywords", description="Ключевые слова"),
        BotCommand(command="sources", description="Источники статей"),
        BotCommand(command="settings", description="Настройки рассылки"),
        BotCommand(command="history", description="История рекомендаций"),
        BotCommand(command="test", description="Тестовый дайджест"),
        BotCommand(command="help", description="Помощь"),
    ])

    logger.info("Starting bot...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        await db.disconnect()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
