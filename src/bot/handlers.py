"""Обработчики команд Telegram бота."""

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from .keyboards import Keyboards
from ..db import Database, UserRepository, PaperRepository
from ..agent.orchestrator import _escape_html, SOURCE_LABELS

# Для тестовой команды
scheduler_service = None


class ProfileStates(StatesGroup):
    """Состояния для редактирования профиля."""
    waiting_interests = State()
    waiting_keywords = State()
    waiting_research_plan = State()


class OnboardingStates(StatesGroup):
    """Состояния онбординга."""
    step_keywords = State()
    step_sources = State()


router = Router()

# Зависимости будут инжектиться через middleware
db: Database | None = None
user_repo: UserRepository | None = None
paper_repo: PaperRepository | None = None


def setup_handlers(
    database: Database,
    user_repository: UserRepository,
    paper_repository: PaperRepository,
) -> Router:
    """Настройка обработчиков с зависимостями."""
    global db, user_repo, paper_repo
    db = database
    user_repo = user_repository
    paper_repo = paper_repository
    return router


def set_scheduler(scheduler):
    """Установить scheduler для тестовой команды."""
    global scheduler_service
    scheduler_service = scheduler


# === Команды ===

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработка /start."""
    if not user_repo or not message.from_user:
        return

    user_id = await user_repo.create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Проверяем: новый ли пользователь (нет keywords)
    profile = await user_repo.get_profile(user_id)
    is_new = not profile or not profile.keywords

    if is_new:
        # Запускаем онбординг
        await state.set_state(OnboardingStates.step_keywords)
        await message.answer(
            f"👋 Привет, {message.from_user.first_name or 'исследователь'}!\n\n"
            "Давай настроим бота за 30 секунд.\n\n"
            "<b>Шаг 1/2:</b> Какие темы тебе интересны? Напиши ключевые слова через запятую.\n"
            "Например: <code>transformer, attention mechanism, LLM, BERT</code>",
            reply_markup=Keyboards.cancel(),
        )
    else:
        # Существующий пользователь — обычное приветствие
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name or 'исследователь'}!\n\n"
            "Используй меню ниже 👇",
            reply_markup=Keyboards.main_menu(),
        )


@router.message(Command("test"))
@router.message(F.text == "🧪 Тестирование рассылки")
async def cmd_test(message: Message):
    """Тестовая отправка дайджеста (не ждать 9:00)."""
    if not user_repo or not message.from_user:
        return

    if not scheduler_service:
        await message.answer("⚠️ Scheduler не инициализирован")
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    profile = await user_repo.get_profile(user.id)
    if not profile or not profile.keywords:
        await message.answer(
            "⚠️ Сначала добавь ключевые слова!\n"
            "Используй /keywords или кнопку «🔑 Ключевые слова»"
        )
        return

    try:
        await scheduler_service.send_test_digest(message.from_user.id)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    """Обработка /help."""
    await message.answer(
        "📖 <b>Как пользоваться ботом</b>\n\n"
        "<b>Профиль</b>\n"
        "• Укажи свои научные интересы (например: machine learning, NLP)\n"
        "• Добавь ключевые слова для поиска\n"
        "• Опционально: опиши текущий план исследований\n\n"
        "<b>Рассылка</b>\n"
        "• Бот ежедневно присылает топ-3 релевантных статьи\n"
        "• Можно настроить время и глубину поиска\n\n"
        "<b>Команды</b>\n"
        "/profile — просмотр профиля\n"
        "/keywords — ключевые слова\n"
        "/sources — выбор источников\n"
        "/settings — настройки рассылки\n"
        "/history — история рекомендаций\n"
        "/test — тестовая отправка дайджеста\n",
    )


@router.message(Command("profile"))
@router.message(F.text == "📋 Мой профиль")
async def cmd_profile(message: Message):
    """Показать профиль пользователя."""
    if not user_repo or not message.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    profile = await user_repo.get_profile(user.id)
    settings = await user_repo.get_settings(user.id)
    sources = await user_repo.get_enabled_sources(user.id)

    keywords_text = ", ".join(profile.keywords) if profile and profile.keywords else "не указаны"
    plan_text = (profile.research_plan[:100] + "...") if profile and profile.research_plan else "не указан"
    sources_text = ", ".join(sources) if sources else "не выбраны"
    status = "✅ Активна" if settings and settings.is_active else "❌ Выключена"

    await message.answer(
        f"👤 <b>Твой профиль</b>\n\n"
        f"🔑 <b>Ключевые слова:</b> {keywords_text}\n"
        f"📝 <b>План исследований:</b> {plan_text}\n"
        f"📚 <b>Источники:</b> {sources_text}\n"
        f"📬 <b>Рассылка:</b> {status}\n",
        reply_markup=Keyboards.profile_actions(),
    )


@router.message(Command("keywords"))
@router.message(F.text == "🔑 Ключевые слова")
async def cmd_keywords(message: Message, state: FSMContext):
    """Редактировать ключевые слова."""
    if not user_repo or not message.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    profile = await user_repo.get_profile(user.id)
    current = ", ".join(profile.keywords) if profile and profile.keywords else "пусто"

    await state.set_state(ProfileStates.waiting_keywords)
    await message.answer(
        f"🔑 <b>Текущие ключевые слова:</b>\n{current}\n\n"
        "Отправь новые ключевые слова через запятую.\n"
        "Например: <code>transformer, attention mechanism, BERT</code>",
        reply_markup=Keyboards.cancel(),
    )


@router.message(Command("sources"))
@router.message(F.text == "📚 Источники")
async def cmd_sources(message: Message):
    """Показать и переключить источники."""
    if not user_repo or not message.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    # Все доступные источники
    all_sources = ["arxiv", "huggingface_papers"]
    enabled = await user_repo.get_enabled_sources(user.id)

    sources = [
        {"name": s, "enabled": s in enabled}
        for s in all_sources
    ]

    await message.answer(
        "📚 <b>Источники статей</b>\n\n"
        "Нажми на источник, чтобы включить/выключить:",
        reply_markup=Keyboards.sources_toggle(sources),
    )


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message):
    """Показать настройки."""
    if not user_repo or not message.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    settings_dict = await _get_settings_dict(user.id)
    await message.answer(
        "⚙️ <b>Настройки рассылки</b>",
        reply_markup=Keyboards.settings_menu(settings_dict),
    )


async def _get_settings_dict(user_id: int) -> dict:
    """Helper: загрузить настройки как dict для клавиатуры."""
    settings = await user_repo.get_settings(user_id)
    return {
        "is_active": settings.is_active if settings else True,
        "send_hour": settings.send_hour if settings else 9,
        "days_depth": settings.days_depth if settings else 7,
        "max_papers": settings.max_papers if settings else 3,
        "digest_frequency": settings.digest_frequency if settings else 1,
    }


# === Callback handlers ===

@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия."""
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()


@router.callback_query(F.data == "edit_interests")
async def callback_edit_interests(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование интересов."""
    await state.set_state(ProfileStates.waiting_interests)
    await callback.message.answer(
        "🎯 Отправь свои научные интересы через запятую.\n"
        "Например: <code>machine learning, computer vision, NLP</code>",
        reply_markup=Keyboards.cancel(),
    )
    await callback.answer()


@router.callback_query(F.data == "edit_keywords")
async def callback_edit_keywords(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование ключевых слов."""
    await state.set_state(ProfileStates.waiting_keywords)
    await callback.message.answer(
        "🔑 Отправь ключевые слова для поиска через запятую.\n"
        "Например: <code>transformer, BERT, attention</code>",
        reply_markup=Keyboards.cancel(),
    )
    await callback.answer()


@router.callback_query(F.data == "edit_research_plan")
async def callback_edit_plan(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование плана исследований."""
    await state.set_state(ProfileStates.waiting_research_plan)
    await callback.message.answer(
        "📝 Опиши свой текущий план исследований.\n"
        "Это поможет боту лучше подбирать статьи.",
        reply_markup=Keyboards.cancel(),
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_notifications")
async def callback_toggle_notifications(callback: CallbackQuery):
    """Переключить рассылку."""
    if not user_repo or not callback.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    settings = await user_repo.get_settings(user.id)
    new_status = not (settings.is_active if settings else True)
    await user_repo.update_settings(user.id, is_active=int(new_status))

    status_text = "включена ✅" if new_status else "выключена ❌"
    await callback.answer(f"Рассылка {status_text}")

    # Обновляем клавиатуру
    settings_dict = await _get_settings_dict(user.id)
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.settings_menu(settings_dict)
    )


@router.callback_query(F.data.startswith("toggle_source:"))
async def callback_toggle_source(callback: CallbackQuery):
    """Переключить источник."""
    if not user_repo or not db or not callback.from_user:
        return

    source_name = callback.data.split(":")[1]
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    # Проверяем текущий статус
    enabled = await user_repo.get_enabled_sources(user.id)
    is_enabled = source_name in enabled

    if is_enabled:
        # Выключаем
        await db.execute(
            "UPDATE user_sources SET enabled = 0 WHERE user_id = ? AND source_name = ?",
            (user.id, source_name),
        )
    else:
        # Включаем (или создаём)
        await db.execute(
            """
            INSERT INTO user_sources (user_id, source_name, enabled)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, source_name) DO UPDATE SET enabled = 1
            """,
            (user.id, source_name),
        )

    await callback.answer(f"{source_name}: {'выключен' if is_enabled else 'включён'}")

    # Обновляем список
    all_sources = ["arxiv", "huggingface_papers"]
    enabled = await user_repo.get_enabled_sources(user.id)
    sources = [{"name": s, "enabled": s in enabled} for s in all_sources]

    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.sources_toggle(sources)
    )


@router.callback_query(F.data.startswith("feedback:"))
async def callback_feedback(callback: CallbackQuery):
    """Обработка feedback по статье."""
    if not paper_repo or not callback.from_user:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка")
        return

    _, action, paper_id = parts
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    feedback_value = 1 if action == "like" else -1
    await paper_repo.set_feedback(user.id, paper_id, feedback_value)

    emoji = "👍" if action == "like" else "👎"
    await callback.answer(f"{emoji} Спасибо за отзыв!")


@router.callback_query(F.data == "go_sources")
async def callback_go_sources(callback: CallbackQuery):
    """Перейти к источникам (из no_results)."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    all_sources = ["arxiv", "huggingface_papers"]
    enabled = await user_repo.get_enabled_sources(user.id)
    sources = [{"name": s, "enabled": s in enabled} for s in all_sources]
    await callback.message.edit_text(
        "📚 <b>Источники статей</b>\n\nНажми на источник, чтобы включить/выключить:",
        reply_markup=Keyboards.sources_toggle(sources),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_settings")
async def callback_back_to_settings(callback: CallbackQuery):
    """Вернуться в меню настроек."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    settings_dict = await _get_settings_dict(user.id)
    await callback.message.edit_text(
        "⚙️ <b>Настройки рассылки</b>",
        reply_markup=Keyboards.settings_menu(settings_dict),
    )
    await callback.answer()


@router.callback_query(F.data == "pick_send_hour")
async def callback_pick_send_hour(callback: CallbackQuery):
    """Показать выбор часа."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    settings = await user_repo.get_settings(user.id)
    current = settings.send_hour if settings else 9
    await callback.message.edit_text(
        "🕐 <b>Выбери время отправки дайджеста</b> (МСК):",
        reply_markup=Keyboards.pick_send_hour(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_hour:"))
async def callback_set_hour(callback: CallbackQuery):
    """Установить час отправки."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    hour = int(callback.data.split(":")[1])
    await user_repo.update_settings(user.id, send_hour=hour)
    await callback.answer(f"Время: {hour}:00")
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.pick_send_hour(hour),
    )


@router.callback_query(F.data == "pick_days_depth")
async def callback_pick_days_depth(callback: CallbackQuery):
    """Показать выбор глубины поиска."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    settings = await user_repo.get_settings(user.id)
    current = settings.days_depth if settings else 7
    await callback.message.edit_text(
        "📅 <b>За сколько дней искать статьи?</b>",
        reply_markup=Keyboards.pick_days_depth(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_depth:"))
async def callback_set_depth(callback: CallbackQuery):
    """Установить глубину поиска."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    depth = int(callback.data.split(":")[1])
    await user_repo.update_settings(user.id, days_depth=depth)
    await callback.answer(f"Глубина: {depth} дней")
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.pick_days_depth(depth),
    )


@router.callback_query(F.data == "pick_max_papers")
async def callback_pick_max_papers(callback: CallbackQuery):
    """Показать выбор количества статей."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    settings = await user_repo.get_settings(user.id)
    current = settings.max_papers if settings else 3
    await callback.message.edit_text(
        "📄 <b>Сколько статей присылать?</b>",
        reply_markup=Keyboards.pick_max_papers(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_max:"))
async def callback_set_max(callback: CallbackQuery):
    """Установить количество статей."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    max_p = int(callback.data.split(":")[1])
    await user_repo.update_settings(user.id, max_papers=max_p)
    await callback.answer(f"Статей: {max_p}")
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.pick_max_papers(max_p),
    )


@router.callback_query(F.data == "pick_frequency")
async def callback_pick_frequency(callback: CallbackQuery):
    """Показать выбор частоты."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    settings = await user_repo.get_settings(user.id)
    current = settings.digest_frequency if settings else 1
    await callback.message.edit_text(
        "🔄 <b>Как часто присылать дайджест?</b>",
        reply_markup=Keyboards.pick_frequency(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_frequency:"))
async def callback_set_frequency(callback: CallbackQuery):
    """Установить частоту."""
    if not user_repo or not callback.from_user:
        return
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    freq = int(callback.data.split(":")[1])
    await user_repo.update_settings(user.id, digest_frequency=freq)
    freq_labels = {1: "Каждый день", 3: "Раз в 3 дня", 7: "Раз в неделю"}
    await callback.answer(freq_labels.get(freq, f"Раз в {freq} дн."))
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.pick_frequency(freq),
    )


# === History handlers ===

@router.message(Command("history"))
@router.message(F.text == "📜 История")
async def cmd_history(message: Message):
    """Показать историю рекомендаций."""
    if not user_repo or not paper_repo or not message.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала выполни /start")
        return

    await _send_history_page(message, user.id, offset=0)


@router.callback_query(F.data.startswith("history_page:"))
async def callback_history_page(callback: CallbackQuery):
    """Пагинация истории."""
    if not user_repo or not paper_repo or not callback.from_user:
        return

    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    offset = int(callback.data.split(":")[1])
    offset = max(0, offset)

    total = await paper_repo.count_sent_papers(user.id)
    papers = await paper_repo.get_sent_papers(user.id, offset=offset, limit=5)

    if not papers:
        await callback.answer("Нет статей")
        return

    text = _format_history_page(papers, offset, total)
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.history_pagination(offset, total),
        disable_web_page_preview=True,
    )
    await callback.answer()


async def _send_history_page(message: Message, user_id: int, offset: int):
    """Отправить страницу истории."""
    total = await paper_repo.count_sent_papers(user_id)

    if total == 0:
        await message.answer("📜 История пуста. Статьи появятся после первого дайджеста.")
        return

    papers = await paper_repo.get_sent_papers(user_id, offset=offset, limit=5)
    text = _format_history_page(papers, offset, total)

    await message.answer(
        text,
        reply_markup=Keyboards.history_pagination(offset, total),
        disable_web_page_preview=True,
    )


def _format_history_page(papers: list[dict], offset: int, total: int) -> str:
    """Форматирование страницы истории."""
    start = offset + 1
    end = offset + len(papers)
    lines = [f"📜 <b>Ваши статьи ({start}-{end} из {total}):</b>\n"]

    for i, p in enumerate(papers, start=start):
        fb = {1: "👍", -1: "👎"}.get(p["feedback"], "—")
        title = _escape_html(p["title"])
        source = SOURCE_LABELS.get(p["source"], p["source"] or "")
        date_str = p["sent_at"][:10] if p["sent_at"] else ""

        line = f"{i}. {fb} {title}"
        if date_str or source:
            line += f"\n   📅 {date_str}"
            if source:
                line += f" · {source}"
        if p["url"]:
            line += f'\n   🔗 <a href="{p["url"]}">Читать</a>'
        lines.append(line)

    return "\n\n".join(lines)


# === Onboarding handlers ===

@router.message(OnboardingStates.step_keywords)
async def onboard_keywords(message: Message, state: FSMContext):
    """Онбординг: сохранение ключевых слов."""
    if not user_repo or not message.from_user or not message.text:
        return
    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    keywords = [k.strip() for k in message.text.split(",") if k.strip()]
    await user_repo.update_profile(user.id, keywords=keywords)

    # Получаем текущие источники
    enabled = await user_repo.get_enabled_sources(user.id)

    await state.set_state(OnboardingStates.step_sources)
    await message.answer(
        f"✅ Отлично: {', '.join(keywords)}\n\n"
        "<b>Шаг 2/2:</b> Выбери источники статей:",
        reply_markup=Keyboards.onboarding_sources(enabled),
    )


@router.callback_query(OnboardingStates.step_sources, F.data.startswith("onboard_source:"))
async def onboard_toggle_source(callback: CallbackQuery, state: FSMContext):
    """Онбординг: переключить источник."""
    if not user_repo or not db or not callback.from_user:
        return
    source_name = callback.data.split(":")[1]
    user = await user_repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    enabled = await user_repo.get_enabled_sources(user.id)
    is_enabled = source_name in enabled

    if is_enabled:
        await db.execute(
            "UPDATE user_sources SET enabled = 0 WHERE user_id = ? AND source_name = ?",
            (user.id, source_name),
        )
    else:
        await db.execute(
            """INSERT INTO user_sources (user_id, source_name, enabled)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, source_name) DO UPDATE SET enabled = 1""",
            (user.id, source_name),
        )

    enabled = await user_repo.get_enabled_sources(user.id)
    await callback.message.edit_reply_markup(
        reply_markup=Keyboards.onboarding_sources(enabled),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.step_sources, F.data == "onboard_done")
async def onboard_done(callback: CallbackQuery, state: FSMContext):
    """Онбординг: завершение."""
    await state.clear()
    await callback.message.edit_text(
        "🎉 <b>Всё настроено!</b>\n\n"
        "Первый дайджест придёт в установленное время.\n"
        "Хочешь получить тестовую подборку прямо сейчас?",
        reply_markup=Keyboards.onboarding_test_offer(),
    )
    await callback.answer()


@router.callback_query(F.data == "onboard_test")
async def onboard_test(callback: CallbackQuery):
    """Запустить тестовый дайджест после онбординга."""
    if not scheduler_service or not callback.from_user:
        await callback.answer("Scheduler не готов")
        return
    await callback.message.edit_text("🚀 Ищу статьи для тебя...")
    try:
        await scheduler_service.send_test_digest(callback.from_user.id)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    await callback.answer()


@router.callback_query(F.data == "onboard_skip")
async def onboard_skip(callback: CallbackQuery):
    """Пропустить тестовый дайджест."""
    await callback.message.edit_text(
        "👌 Хорошо! Дайджест придёт по расписанию.\n"
        "Используй меню ниже 👇",
    )
    await callback.message.answer(
        "Главное меню:",
        reply_markup=Keyboards.main_menu(),
    )
    await callback.answer()


# === State handlers ===

@router.message(ProfileStates.waiting_interests)
async def process_interests(message: Message, state: FSMContext):
    """Сохранение интересов."""
    if not user_repo or not message.from_user or not message.text:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    interests = [i.strip() for i in message.text.split(",") if i.strip()]
    await user_repo.update_profile(user.id, interests=interests)
    await state.clear()

    await message.answer(
        f"✅ Интересы сохранены:\n{', '.join(interests)}",
        reply_markup=Keyboards.main_menu(),
    )


@router.message(ProfileStates.waiting_keywords)
async def process_keywords(message: Message, state: FSMContext):
    """Сохранение ключевых слов."""
    if not user_repo or not message.from_user or not message.text:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    keywords = [k.strip() for k in message.text.split(",") if k.strip()]
    await user_repo.update_profile(user.id, keywords=keywords)
    await state.clear()

    await message.answer(
        f"✅ Ключевые слова сохранены:\n{', '.join(keywords)}",
        reply_markup=Keyboards.main_menu(),
    )


@router.message(ProfileStates.waiting_research_plan)
async def process_research_plan(message: Message, state: FSMContext):
    """Сохранение плана исследований."""
    if not user_repo or not message.from_user or not message.text:
        return

    user = await user_repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    await user_repo.update_profile(user.id, research_plan=message.text)
    await state.clear()

    await message.answer(
        "✅ План исследований сохранён!",
        reply_markup=Keyboards.main_menu(),
    )
