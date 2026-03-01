"""Тест базы данных."""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import config
from db import Database, UserRepository, PaperRepository


async def main():
    print("=" * 60)
    print("Тест базы данных SQLite")
    print("=" * 60)

    db = Database(config.db.path)

    print(f"\nПуть к БД: {config.db.path}")

    # Подключение
    print("\n--- Подключение ---")
    try:
        await db.connect()
        print("✅ База данных подключена")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    # Тест репозиториев
    user_repo = UserRepository(db)
    paper_repo = PaperRepository(db)

    # Создание пользователя
    print("\n--- Создание тестового пользователя ---")
    try:
        user_id = await user_repo.create_user(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
        )
        print(f"✅ Пользователь создан, ID: {user_id}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Получение пользователя
    print("\n--- Получение пользователя ---")
    try:
        user = await user_repo.get_user_by_telegram_id(123456789)
        if user:
            print(f"✅ Пользователь найден: {user.username}")
        else:
            print("❌ Пользователь не найден")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Обновление профиля
    print("\n--- Обновление профиля ---")
    try:
        await user_repo.update_profile(
            user_id=user_id,
            interests=["machine learning", "NLP"],
            keywords=["transformer", "bert", "gpt"],
        )
        profile = await user_repo.get_profile(user_id)
        print(f"✅ Профиль обновлён:")
        print(f"   Интересы: {profile.interests}")
        print(f"   Ключевые слова: {profile.keywords}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Настройки
    print("\n--- Настройки ---")
    try:
        settings = await user_repo.get_settings(user_id)
        print(f"✅ Настройки:")
        print(f"   Время: {settings.send_hour}:00")
        print(f"   Глубина: {settings.days_depth} дней")
        print(f"   Активна: {settings.is_active}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Активные пользователи
    print("\n--- Активные пользователи ---")
    try:
        users = await user_repo.get_active_users()
        print(f"✅ Найдено активных: {len(users)}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    await db.disconnect()
    print("\n✅ Тест завершён")


if __name__ == "__main__":
    asyncio.run(main())
