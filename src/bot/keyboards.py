"""Клавиатуры для Telegram бота."""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


class Keyboards:
    """Фабрика клавиатур."""

    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Главное меню."""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📋 Мой профиль"), KeyboardButton(text="📜 История")],
                [KeyboardButton(text="🔑 Ключевые слова"), KeyboardButton(text="📚 Источники")],
                [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")],
                [KeyboardButton(text="🧪 Тестирование рассылки")],
            ],
            resize_keyboard=True,
        )

    @staticmethod
    def profile_actions() -> InlineKeyboardMarkup:
        """Действия с профилем."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔑 Изменить ключевые слова",
                        callback_data="edit_keywords",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📝 Добавить план исследований",
                        callback_data="edit_research_plan",
                    )
                ],
            ]
        )

    @staticmethod
    def sources_toggle(sources: list[dict]) -> InlineKeyboardMarkup:
        """Список источников с переключателями."""
        buttons = []
        for source in sources:
            status = "✅" if source["enabled"] else "❌"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {source['name']}",
                    callback_data=f"toggle_source:{source['name']}",
                )
            ])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def settings_menu(settings: dict) -> InlineKeyboardMarkup:
        """Меню настроек."""
        status = "🔔 Вкл" if settings.get("is_active") else "🔕 Выкл"
        freq = settings.get("digest_frequency", 1)
        freq_labels = {1: "Каждый день", 3: "Раз в 3 дня", 7: "Раз в неделю"}
        freq_text = freq_labels.get(freq, f"Раз в {freq} дн.")

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"Рассылка: {status}",
                    callback_data="toggle_notifications",
                )],
                [InlineKeyboardButton(
                    text=f"🕐 Время: {settings.get('send_hour', 9)}:00",
                    callback_data="pick_send_hour",
                )],
                [InlineKeyboardButton(
                    text=f"📅 Глубина: {settings.get('days_depth', 7)} дней",
                    callback_data="pick_days_depth",
                )],
                [InlineKeyboardButton(
                    text=f"📄 Статей: {settings.get('max_papers', 3)}",
                    callback_data="pick_max_papers",
                )],
                [InlineKeyboardButton(
                    text=f"🔄 Частота: {freq_text}",
                    callback_data="pick_frequency",
                )],
            ]
        )

    @staticmethod
    def pick_send_hour(current: int) -> InlineKeyboardMarkup:
        """Выбор часа отправки."""
        hours = [6, 7, 8, 9, 10, 11, 12, 18]
        buttons = []
        row = []
        for h in hours:
            label = f"✅ {h}:00" if h == current else f"{h}:00"
            row.append(InlineKeyboardButton(text=label, callback_data=f"set_hour:{h}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def pick_days_depth(current: int) -> InlineKeyboardMarkup:
        """Выбор глубины поиска."""
        options = [3, 7, 14, 30]
        buttons = []
        for d in options:
            label = f"✅ {d} дней" if d == current else f"{d} дней"
            buttons.append(InlineKeyboardButton(text=label, callback_data=f"set_depth:{d}"))
        return InlineKeyboardMarkup(inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")],
        ])

    @staticmethod
    def pick_max_papers(current: int) -> InlineKeyboardMarkup:
        """Выбор количества статей."""
        options = [1, 3, 5]
        buttons = []
        for n in options:
            label = f"✅ {n}" if n == current else str(n)
            buttons.append(InlineKeyboardButton(text=label, callback_data=f"set_max:{n}"))
        return InlineKeyboardMarkup(inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")],
        ])

    @staticmethod
    def pick_frequency(current: int) -> InlineKeyboardMarkup:
        """Выбор частоты рассылки."""
        options = [(1, "Каждый день"), (3, "Раз в 3 дня"), (7, "Раз в неделю")]
        buttons = []
        for val, text in options:
            label = f"✅ {text}" if val == current else text
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"set_frequency:{val}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def paper_feedback(paper_id: str) -> InlineKeyboardMarkup:
        """Кнопки обратной связи для статьи."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👍 Полезно",
                        callback_data=f"feedback:like:{paper_id}",
                    ),
                    InlineKeyboardButton(
                        text="💡 Можешь лучше",
                        callback_data=f"feedback:dislike:{paper_id}",
                    ),
                ]
            ]
        )

    @staticmethod
    def cancel() -> InlineKeyboardMarkup:
        """Кнопка отмены."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
            ]
        )

    @staticmethod
    def confirm_cancel() -> InlineKeyboardMarkup:
        """Подтверждение/отмена."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
                ]
            ]
        )

    @staticmethod
    def history_pagination(offset: int, total: int, page_size: int = 5) -> InlineKeyboardMarkup:
        """Пагинация для истории."""
        buttons = []
        if offset > 0:
            buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"history_page:{offset - page_size}"))
        if offset + page_size < total:
            buttons.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"history_page:{offset + page_size}"))
        if not buttons:
            return InlineKeyboardMarkup(inline_keyboard=[])
        return InlineKeyboardMarkup(inline_keyboard=[buttons])

    @staticmethod
    def onboarding_sources(enabled: list[str]) -> InlineKeyboardMarkup:
        """Источники для онбординга (с кнопкой Готово)."""
        all_sources = ["arxiv", "huggingface_papers"]
        buttons = []
        for source in all_sources:
            status = "✅" if source in enabled else "☐"
            buttons.append([InlineKeyboardButton(
                text=f"{status} {source}",
                callback_data=f"onboard_source:{source}",
            )])
        buttons.append([InlineKeyboardButton(
            text="Готово ➡️",
            callback_data="onboard_done",
        )])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def no_results_actions() -> InlineKeyboardMarkup:
        """Кнопки при отсутствии релевантных статей."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔑 Изменить ключевые слова",
                    callback_data="edit_keywords",
                )],
                [InlineKeyboardButton(
                    text="📅 Увеличить глубину поиска",
                    callback_data="pick_days_depth",
                )],
            ]
        )

    @staticmethod
    def onboarding_test_offer() -> InlineKeyboardMarkup:
        """Предложение тестового дайджеста после онбординга."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚀 Да, пришли!", callback_data="onboard_test"),
                    InlineKeyboardButton(text="Подожду", callback_data="onboard_skip"),
                ]
            ]
        )
