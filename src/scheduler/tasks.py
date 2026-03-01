"""Планировщик задач для ежедневной рассылки."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from ..db import Database, UserRepository, PaperRepository
from ..llm import LLMClient
from ..agent import PaperAgent, format_recommendation_message, _escape_html


logger = logging.getLogger(__name__)


class SchedulerService:
    """Сервис планирования рассылок."""

    def __init__(
        self,
        bot: Bot,
        db: Database,
        user_repo: UserRepository,
        paper_repo: PaperRepository,
        llm_client: LLMClient,
    ):
        self.bot = bot
        self.db = db
        self.user_repo = user_repo
        self.paper_repo = paper_repo
        self.llm_client = llm_client

        self.scheduler = AsyncIOScheduler()
        self.agent = PaperAgent(llm_client, user_repo, paper_repo)

    def start(self):
        """Запуск планировщика."""
        self.scheduler.add_job(
            self.hourly_check,
            CronTrigger(minute=0, timezone="Europe/Moscow"),
            id="hourly_check",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Scheduler started. Hourly check every :00 MSK")

    def stop(self):
        """Остановка планировщика."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    async def hourly_check(self):
        """Ежечасная проверка: кому отправить дайджест."""
        from datetime import datetime as _dt
        from datetime import timezone as _tz
        from zoneinfo import ZoneInfo

        moscow = ZoneInfo("Europe/Moscow")
        current_hour = _dt.now(moscow).hour
        logger.info(f"Hourly check: hour={current_hour} MSK")

        users = await self.user_repo.get_users_for_hour(current_hour)
        logger.info(f"Found {len(users)} users for hour {current_hour}")

        for user in users:
            try:
                await self._send_digest_to_user(user.id, user.telegram_id)
                await self.user_repo.update_last_digest_at(user.id)
            except Exception as e:
                logger.error(f"Error sending digest to user {user.id}: {e}")

        logger.info(f"Hourly check completed for hour {current_hour}")

    async def _send_digest_to_user(self, user_id: int, telegram_id: int):
        """Отправка дайджеста одному пользователю."""
        settings = await self.user_repo.get_settings(user_id)
        max_papers = settings.max_papers if settings else 3

        # Callback для статусов
        async def send_status(text):
            await self.bot.send_message(chat_id=telegram_id, text=text)

        # Получаем рекомендации
        recommendations = await self.agent.get_recommendations(
            user_id=user_id,
            max_papers=max_papers,
            on_status=send_status,
        )

        if not recommendations:
            logger.info(f"No recommendations for user {user_id}")
            from ..bot.keyboards import Keyboards
            await self.bot.send_message(
                chat_id=telegram_id,
                text="📭 Сегодня не нашлось новых релевантных статей.\n\n"
                     "Что можно сделать:\n"
                     "• Добавить больше ключевых слов\n"
                     "• Увеличить глубину поиска (например, 14 дней)",
                reply_markup=Keyboards.no_results_actions(),
            )
            return

        # Отправляем заголовок
        date_str = datetime.now().strftime("%d %B %Y")
        await self.bot.send_message(
            chat_id=telegram_id,
            text=f"📬 <b>Ваша научная подборка за {date_str}</b>\n\n"
                 f"Найдено {len(recommendations)} релевантных статей:",
        )

        # Отправляем каждую статью отдельным сообщением
        from ..bot.keyboards import Keyboards

        for rec in recommendations:
            message_text = format_recommendation_message(rec)

            await self.bot.send_message(
                chat_id=telegram_id,
                text=message_text,
                reply_markup=Keyboards.paper_feedback(rec.paper.id),
                disable_web_page_preview=True,
            )

            # Отмечаем как отправленную
            await self.paper_repo.mark_paper_sent(
                user_id=user_id,
                paper_id=rec.paper.id,
                title=rec.paper.title,
                url=rec.paper.url,
                source=rec.paper.source,
            )

        logger.info(f"Sent {len(recommendations)} papers to user {user_id}")

    async def send_test_digest(self, telegram_id: int):
        """Тестовая отправка (для отладки)."""
        user = await self.user_repo.get_user_by_telegram_id(telegram_id)
        if not user:
            logger.error(f"User not found: {telegram_id}")
            raise ValueError("Пользователь не найден")

        try:
            await self._send_digest_to_user(user.id, telegram_id)
        except Exception as e:
            logger.error(f"Test digest error for {telegram_id}: {e}")
            await self.bot.send_message(
                chat_id=telegram_id,
                text=f"❌ Ошибка при поиске статей:\n<code>{_escape_html(str(e)[:200])}</code>",
            )
            raise
