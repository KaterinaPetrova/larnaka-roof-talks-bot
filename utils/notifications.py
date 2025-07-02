import logging
from datetime import datetime, timedelta
from aiogram import Bot
from config import WAITLIST_TIMEOUT_HOURS, NOTIFICATION_CHAT_ID
from database.db import get_event, get_registration, update_waitlist_status
from keyboards.keyboards import get_waitlist_notification_keyboard

# Initialize logger
logger = logging.getLogger(__name__)

async def send_registration_confirmation(bot: Bot, user_id: int, event_id: int, role: str):
    """Send confirmation message after successful registration."""
    event = await get_event(event_id)

    if role == "speaker":
        message = (
            f"Ты зарегистрирован(а) как спикер! 🎉\n"
            f"Мероприятие: {event['title']} — {event['date']}\n"
            f"Мы напомним тебе ближе к дате.\n"
            f"До встречи на крыше!"
        )
    else:
        message = (
            f"Ты в списке слушателей! 🔥\n"
            f"Мероприятие: {event['title']} — {event['date']}\n"
            f"Приходи, будет интересно!"
        )

    try:
        await bot.send_message(user_id, message)
        logger.info(f"Sent registration confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        logger.error(f"Failed to send registration confirmation: {e}")

async def send_waitlist_confirmation(bot: Bot, user_id: int, event_id: int, role: str):
    """Send confirmation message after adding to waitlist."""
    event = await get_event(event_id)

    message = (
        f"Ты в списке ожидания для мероприятия {event['title']} — {event['date']}.\n"
        f"Роль: {'Спикер' if role == 'speaker' else 'Слушатель'}\n"
        f"Если кто-то отменит участие — мы напишем тебе!"
    )

    try:
        await bot.send_message(user_id, message)
        logger.info(f"Sent waitlist confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        logger.error(f"Failed to send waitlist confirmation: {e}")

async def send_waitlist_notification(bot: Bot, user_id: int, waitlist_id: int, event_id: int, role: str):
    """Send notification to the next person in waitlist."""
    event = await get_event(event_id)

    message = (
        f"Появилось свободное место на мероприятии {event['title']} — {event['date']}!\n"
        f"Роль: {'Спикер' if role == 'speaker' else 'Слушатель'}\n"
        f"Хочешь участвовать?\n\n"
        f"У тебя есть 2 часа на ответ."
    )

    keyboard = get_waitlist_notification_keyboard(waitlist_id)

    try:
        await bot.send_message(user_id, message, reply_markup=keyboard)

        # Update waitlist status to notified
        notified_at = datetime.now().isoformat()
        await update_waitlist_status(waitlist_id, "notified", notified_at)

        logger.info(f"Sent waitlist notification to user {user_id} for event {event_id}")
    except Exception as e:
        logger.error(f"Failed to send waitlist notification: {e}")


async def send_talk_update_confirmation(bot: Bot, user_id: int, registration_id: int, field: str):
    """Send confirmation after talk update."""
    registration = await get_registration(registration_id)
    event = await get_event(registration["event_id"])

    field_name = {
        "topic": "тема",
        "description": "описание",
        "has_presentation": "слайды"
    }.get(field, field)

    message = (
        f"Информация о твоем докладе обновлена!\n"
        f"Изменено поле: {field_name}\n"
        f"Мероприятие: {event['title']} — {event['date']}"
    )

    try:
        await bot.send_message(user_id, message)
        logger.info(f"Sent talk update confirmation to user {user_id} for registration {registration_id}")
    except Exception as e:
        logger.error(f"Failed to send talk update confirmation: {e}")

async def send_cancellation_confirmation(bot: Bot, user_id: int, event_id: int, role: str):
    """Send confirmation after registration cancellation."""
    event = await get_event(event_id)

    role_text = "спикера" if role == "speaker" else "участника"
    message = (
        f"Твоя регистрация {role_text} на мероприятие {event['title']} — {event['date']} отменена.\n"
        f"Если передумаешь, можешь зарегистрироваться снова, если будут свободные места."
    )

    try:
        await bot.send_message(user_id, message)
        logger.info(f"Sent cancellation confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        logger.error(f"Failed to send cancellation confirmation: {e}")


async def check_expired_waitlist_notifications(bot: Bot):
    """Check for expired waitlist notifications and update their status."""
    from database.db import get_next_from_waitlist
    import aiosqlite
    from config import DB_NAME, WAITLIST_TIMEOUT_HOURS
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)

    try:
        # Calculate the expiration time
        expiration_time = (datetime.now() - timedelta(hours=WAITLIST_TIMEOUT_HOURS)).isoformat()

        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row

            # Find all expired waitlist notifications
            cursor = await db.execute(
                "SELECT * FROM waitlist WHERE status = 'notified' AND notified_at < ?",
                (expiration_time,)
            )
            expired_entries = await cursor.fetchall()

            for entry in expired_entries:
                # Update status to expired
                await db.execute(
                    "UPDATE waitlist SET status = 'expired' WHERE id = ?",
                    (entry["id"],)
                )

                # Check if there's another person on the waitlist
                next_waitlist = await get_next_from_waitlist(entry["event_id"], entry["role"])

                if next_waitlist:
                    # Send notification to the next person on the waitlist
                    await send_waitlist_notification(
                        bot,
                        next_waitlist["user_id"],
                        next_waitlist["id"],
                        next_waitlist["event_id"],
                        next_waitlist["role"]
                    )

                    logger.info(f"Notified next person {next_waitlist['user_id']} on waitlist for event {next_waitlist['event_id']} after expiration")

                logger.info(f"Expired waitlist entry {entry['id']} for user {entry['user_id']} and event {entry['event_id']}")

            await db.commit()

            return len(expired_entries)
    except Exception as e:
        logger.error(f"Error checking expired waitlist notifications: {e}")
        return 0

async def send_admin_notification(bot: Bot, notification_type: str, event_id: int, user_info: dict, role: str = None, additional_info: str = None):
    """Send notification to admin chat about changes in participants or speakers.

    Args:
        bot: Bot instance
        notification_type: Type of notification (registration, cancellation, update, waitlist)
        event_id: ID of the event
        user_info: Dictionary with user information (first_name, last_name, etc.)
        role: Role of the user (speaker or participant)
        additional_info: Any additional information to include in the notification
    """
    if not NOTIFICATION_CHAT_ID:
        logger.warning("NOTIFICATION_CHAT_ID not set, skipping admin notification")
        return

    try:
        event = await get_event(event_id)
        if not event:
            logger.error(f"Failed to get event {event_id} for admin notification")
            return

        user_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}"
        role_text = "спикера" if role == "speaker" else "участника"

        if notification_type == "registration":
            message = (
                f"🆕 Новая регистрация {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"

        elif notification_type == "cancellation":
            message = (
                f"❌ Отмена регистрации {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"

        elif notification_type == "update":
            message = (
                f"✏️ Обновление информации {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}"
            )
            if additional_info:
                message += f"\nИзменено: {additional_info}"

        elif notification_type == "waitlist":
            message = (
                f"⏳ Новый пользователь в списке ожидания!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}\n"
                f"Роль: {'Спикер' if role == 'speaker' else 'Участник'}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"
        else:
            message = (
                f"ℹ️ Уведомление о мероприятии!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}\n"
                f"Действие: {notification_type}"
            )

        await bot.send_message(NOTIFICATION_CHAT_ID, message)
        logger.info(f"Sent admin notification about {notification_type} for event {event_id}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
