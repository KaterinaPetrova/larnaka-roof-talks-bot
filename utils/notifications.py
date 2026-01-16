import logging
from datetime import datetime, timedelta
from aiogram import Bot
from config import WAITLIST_TIMEOUT_HOURS, NOTIFICATION_CHAT_ID
from database.db import get_event, get_registration, update_waitlist_status
from keyboards.keyboards import get_waitlist_notification_keyboard
from utils.logging import log_exception

# Initialize logger
logger = logging.getLogger(__name__)

async def send_registration_confirmation(bot: Bot, user_id: int, event_id: int, role: str):
    """Send confirmation message after successful registration."""
    event = await get_event(event_id)

    # Handle case when event is None
    if not event:
        logger.error(f"Event {event_id} not found when sending registration confirmation to user {user_id}")
        message = (
            f"Ты успешно зарегистрирован(а)! 🎉\n"
            f"Мы напомним тебе ближе к дате мероприятия.\n"
            f"До встречи на крыше!"
        )
    elif role == "speaker":
        message = (
            f"Ты зарегистрирован(а) как спикер! 🎉\n"
            f"Мероприятие: {event['title']} — {event['date']}\n"
            f"Мы напомним тебе ближе к дате.\n"
            f"До встречи на крыше!"
        )
        # Add chat link if available
        try:
            if event['chat_link']:
                message += f"\n\n💬 Ссылка на чат мероприятия: {event['chat_link']}"
        except (KeyError, TypeError, IndexError):
            pass
    else:
        message = (
            f"Ты в списке слушателей! 🔥\n"
            f"Мероприятие: {event['title']} — {event['date']}\n"
            f"Приходи, будет интересно!"
        )
        # Add chat link if available
        try:
            if event['chat_link']:
                message += f"\n\n💬 Ссылка на чат мероприятия: {event['chat_link']}"
        except (KeyError, TypeError, IndexError):
            pass

    try:
        await bot.send_message(user_id, message)
        logger.warning(f"Sent registration confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "message": message,
                "event": event
            },
            user_id=user_id,
            event_id=event_id,
            message="Failed to send registration confirmation"
        )

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
        logger.warning(f"Sent waitlist confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "message": message,
                "event": event
            },
            user_id=user_id,
            event_id=event_id,
            message="Failed to send waitlist confirmation"
        )

async def send_waitlist_notification(bot: Bot, user_id: int, waitlist_id: int, event_id: int, role: str):
    """Send notification to the next person in waitlist."""
    event = await get_event(event_id)

    message = (
        f"Появилось свободное место на мероприятии {event['title']} — {event['date']}!\n"
        f"Роль: {'Спикер' if role == 'speaker' else 'Слушатель'}\n"
        f"Хочешь участвовать?\n\n"
        f"У тебя есть {WAITLIST_TIMEOUT_HOURS} часа на ответ."
    )

    keyboard = get_waitlist_notification_keyboard(waitlist_id)

    try:
        await bot.send_message(user_id, message, reply_markup=keyboard)

        # Update waitlist status to notified
        notified_at = datetime.now().isoformat()
        await update_waitlist_status(waitlist_id, "notified", notified_at)

        logger.warning(f"Sent waitlist notification to user {user_id} for event {event_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "message": message,
                "event": event,
                "waitlist_id": waitlist_id,
                "role": role,
                "keyboard": str(keyboard)
            },
            user_id=user_id,
            event_id=event_id,
            message="Failed to send waitlist notification"
        )


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
        logger.warning(f"Sent talk update confirmation to user {user_id} for registration {registration_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "message": message,
                "registration": registration,
                "registration_id": registration_id,
                "field": field
            },
            user_id=user_id,
            event_id=registration.get("event_id") if registration else None,
            message="Failed to send talk update confirmation"
        )

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
        logger.warning(f"Sent cancellation confirmation to user {user_id} for event {event_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "message": message,
                "event": event,
                "role": role
            },
            user_id=user_id,
            event_id=event_id,
            message="Failed to send cancellation confirmation"
        )


async def check_expired_waitlist_notifications(bot: Bot):
    """Check for expired waitlist notifications and update their status.

    First, process all expired waitlist entries by updating their status and sending notifications.
    Then, check for available spots in ALL open events and notify users from the waitlist.
    """
    from database.db import (
        get_expired_waitlist_notifications, 
        update_expired_waitlist_entry,
        get_available_spots,
        get_next_from_waitlist,
        get_event_waitlist,
        count_notified_waitlist_users,
        get_open_events
    )
    from config import WAITLIST_TIMEOUT_HOURS, ROLE_SPEAKER, ROLE_PARTICIPANT
    from datetime import datetime, timedelta
    from utils.text_constants import WAITLIST_EXPIRED_MESSAGE

    logger = logging.getLogger(__name__)

    logger.warning(f"Starting waitlist scheduler check at {datetime.now().isoformat()}")
    processed_count = 0
    notified_total = 0

    try:
        # Calculate the expiration time
        expiration_time = (datetime.now() - timedelta(hours=WAITLIST_TIMEOUT_HOURS)).isoformat()
        logger.warning(f"Checking for waitlist notifications that expired before {expiration_time}")

        # Step 1: Get all expired waitlist entries
        expired_entries = await get_expired_waitlist_notifications(expiration_time)
        logger.warning(f"Found {len(expired_entries)} expired waitlist notifications")

        # Step 2: Process each expired entry
        for entry in expired_entries:
            # Update status to expired
            success = await update_expired_waitlist_entry(entry["id"])
            if not success:
                logger.error(f"Failed to update waitlist entry {entry['id']} to expired")
                continue

            # Send expiration notification to the user
            try:
                await bot.send_message(entry["user_id"], WAITLIST_EXPIRED_MESSAGE)
                logger.warning(f"Sent expiration notification to user {entry['user_id']} for event {entry['event_id']}")
            except Exception as e:
                logger.error(f"Failed to send expiration notification to user {entry['user_id']}: {str(e)}")

            logger.warning(f"Expired waitlist entry {entry['id']} for user {entry['user_id']} and event {entry['event_id']}")
            processed_count += 1

        # Step 3: Check ALL open events for available spots and notify waitlisted users
        events = await get_open_events()
        logger.warning(f"Checking {len(events)} open events for available waitlist spots")
        
        roles = [ROLE_SPEAKER, ROLE_PARTICIPANT]

        for event in events:
            event_id = event["id"]
            
            for role in roles:
                # Check how many spots are available
                available_spots = await get_available_spots(event_id, role)

                if available_spots <= 0:
                    continue

                # Get count of already notified users
                already_notified_count = await count_notified_waitlist_users(event_id, role)

                # Calculate actual available spots considering already notified users
                actual_available_spots = max(0, available_spots - already_notified_count)

                logger.warning(f"Event {event_id} role {role}: {available_spots} available spots, "
                              f"{already_notified_count} already notified, "
                              f"{actual_available_spots} actual available")

                if actual_available_spots <= 0:
                    continue

                # Get users from waitlist for this event and role
                waitlist_entries = await get_event_waitlist(event_id, role)

                # Notify up to actual_available_spots users
                notified_count = 0
                for entry in waitlist_entries:
                    if notified_count >= actual_available_spots:
                        break

                    # Only notify users with 'active' status
                    if entry["status"] != "active":
                        continue

                    # Send notification to the user
                    try:
                        await send_waitlist_notification(
                            bot,
                            entry["user_id"],
                            entry["id"],
                            entry["event_id"],
                            entry["role"]
                        )
                        logger.warning(f"Notified user {entry['user_id']} from waitlist for event {entry['event_id']} with role {entry['role']}")
                        notified_count += 1
                        notified_total += 1
                    except Exception as e:
                        logger.error(f"Failed to send waitlist notification to user {entry['user_id']}: {str(e)}")

                if notified_count > 0:
                    logger.warning(f"Notified {notified_count} users from waitlist for event {event_id} with role {role}")

        logger.warning(f"Waitlist scheduler check completed. Processed {processed_count} expired notifications, notified {notified_total} users from waitlist.")
        return processed_count
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "expiration_time": expiration_time if 'expiration_time' in locals() else None
            },
            message="Error checking expired waitlist notifications"
        )
        logger.warning(f"Waitlist scheduler check failed with error: {str(e)}")
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
        username_display = f" (@{user_info.get('username')})" if user_info.get('username') else ""
        role_text = "спикера" if role == "speaker" else "участника"

        if notification_type == "registration":
            message = (
                f"🆕 Новая регистрация {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}{username_display}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"

        elif notification_type == "cancellation":
            message = (
                f"❌ Отмена регистрации {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}{username_display}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"

        elif notification_type == "update":
            message = (
                f"✏️ Обновление информации {role_text}!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}{username_display}"
            )
            if additional_info:
                message += f"\nИзменено: {additional_info}"

        elif notification_type == "waitlist":
            message = (
                f"⏳ Новый пользователь в списке ожидания!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}{username_display}\n"
                f"Роль: {'Спикер' if role == 'speaker' else 'Участник'}"
            )
            if role == "speaker" and user_info.get('topic'):
                message += f"\nТема: {user_info.get('topic')}"
        else:
            message = (
                f"ℹ️ Уведомление о мероприятии!\n"
                f"Мероприятие: {event['title']} ({event['date']})\n"
                f"Пользователь: {user_name}{username_display}\n"
                f"Действие: {notification_type}"
            )

        await bot.send_message(NOTIFICATION_CHAT_ID, message)
        logger.warning(f"Sent admin notification about {notification_type} for event {event_id}")
    except Exception as e:
        log_exception(
            exception=e,
            context={
                "notification_type": notification_type,
                "user_info": user_info,
                "role": role,
                "additional_info": additional_info,
                "message": message if 'message' in locals() else None
            },
            event_id=event_id,
            message="Failed to send admin notification"
        )


async def process_waitlist_manually(bot: Bot):
    """Manually process waitlist: update expired entries and send notifications to all open events.

    This function is called by admin to:
    1. Check and update expired waitlist notifications (status 'notified' -> 'expired')
    2. Check all open events for available spots and send notifications to waitlist users

    Returns:
        dict: Summary with counts of expired processed and notified users
    """
    from database.db import (
        get_expired_waitlist_notifications,
        update_expired_waitlist_entry,
        get_available_spots,
        get_event_waitlist,
        count_notified_waitlist_users,
        get_open_events
    )
    from config import WAITLIST_TIMEOUT_HOURS, ROLE_SPEAKER, ROLE_PARTICIPANT
    from datetime import datetime, timedelta
    from utils.text_constants import WAITLIST_EXPIRED_MESSAGE

    logger = logging.getLogger(__name__)

    logger.warning(f"Starting manual waitlist processing at {datetime.now().isoformat()}")

    result = {
        "expired_processed": 0,
        "notified_users": 0,
        "events_processed": 0,
        "errors": []
    }

    try:
        # Step 1: Process expired waitlist notifications
        expiration_time = (datetime.now() - timedelta(hours=WAITLIST_TIMEOUT_HOURS)).isoformat()
        logger.warning(f"Checking for waitlist notifications that expired before {expiration_time}")

        expired_entries = await get_expired_waitlist_notifications(expiration_time)
        logger.warning(f"Found {len(expired_entries)} expired waitlist notifications")

        for entry in expired_entries:
            success = await update_expired_waitlist_entry(entry["id"])
            if not success:
                logger.error(f"Failed to update waitlist entry {entry['id']} to expired")
                result["errors"].append(f"Failed to expire entry {entry['id']}")
                continue

            # Send expiration notification to the user
            try:
                await bot.send_message(entry["user_id"], WAITLIST_EXPIRED_MESSAGE)
                logger.warning(f"Sent expiration notification to user {entry['user_id']} for event {entry['event_id']}")
            except Exception as e:
                logger.error(f"Failed to send expiration notification to user {entry['user_id']}: {str(e)}")
                result["errors"].append(f"Failed to notify user {entry['user_id']} about expiration")

            result["expired_processed"] += 1

        # Step 2: Process ALL open events for available spots
        events = await get_open_events()
        logger.warning(f"Found {len(events)} open events to process")

        roles = [ROLE_SPEAKER, ROLE_PARTICIPANT]

        for event in events:
            event_id = event["id"]
            result["events_processed"] += 1

            for role in roles:
                # Check how many spots are available
                available_spots = await get_available_spots(event_id, role)

                if available_spots <= 0:
                    logger.warning(f"No available spots for event {event_id} with role {role}")
                    continue

                # Get count of already notified users
                already_notified_count = await count_notified_waitlist_users(event_id, role)

                # Calculate actual available spots considering already notified users
                actual_available_spots = max(0, available_spots - already_notified_count)

                logger.warning(f"Event {event_id} role {role}: {available_spots} available spots, "
                              f"{already_notified_count} already notified, "
                              f"{actual_available_spots} actual available")

                if actual_available_spots <= 0:
                    logger.warning(f"No actual available spots for event {event_id} with role {role} after considering notified users")
                    continue

                # Get users from waitlist for this event and role
                waitlist_entries = await get_event_waitlist(event_id, role)

                # Notify up to actual_available_spots users
                notified_count = 0
                for entry in waitlist_entries:
                    if notified_count >= actual_available_spots:
                        break

                    # Only notify users with 'active' status
                    if entry["status"] != "active":
                        continue

                    # Send notification to the user
                    try:
                        await send_waitlist_notification(
                            bot,
                            entry["user_id"],
                            entry["id"],
                            entry["event_id"],
                            entry["role"]
                        )
                        logger.warning(f"Notified user {entry['user_id']} from waitlist for event {entry['event_id']} with role {entry['role']}")
                        notified_count += 1
                        result["notified_users"] += 1
                    except Exception as e:
                        logger.error(f"Failed to send waitlist notification to user {entry['user_id']}: {str(e)}")
                        result["errors"].append(f"Failed to notify user {entry['user_id']}")

                logger.warning(f"Notified {notified_count} users from waitlist for event {event_id} with role {role}")

        logger.warning(f"Manual waitlist processing completed. Expired: {result['expired_processed']}, Notified: {result['notified_users']}")
        return result

    except Exception as e:
        log_exception(
            exception=e,
            context={
                "expiration_time": expiration_time if 'expiration_time' in locals() else None
            },
            message="Error during manual waitlist processing"
        )
        result["errors"].append(f"General error: {str(e)}")
        return result
