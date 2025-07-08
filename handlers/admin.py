import logging
import os
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import BOT_TOKEN, REVOLUT_DONATION_URL, DB_NAME, BACKUP_CHAT_ID
from utils import log_exception
from utils.notifications import send_admin_notification
from utils.validation import has_available_slots
from utils.validation_helpers import (
    validate_waitlist_entry,
    validate_waitlist_status,
    validate_event,
    validate_registration,
    validate_registration_owner,
    handle_error_and_return
)

from database.db import (
    is_admin,
    add_admin,
    get_open_events,
    get_event_statistics,
    get_event_participants,
    get_event_speakers,
    register_user,
    cancel_registration,
    get_registration,
    get_event,
    update_registration
)
from keyboards.keyboards import (
    get_admin_keyboard,
    get_admin_events_keyboard,
    get_admin_role_keyboard,
    get_admin_user_list_keyboard,
    get_admin_confirmation_keyboard,
    get_start_keyboard,
    get_payment_confirmation_keyboard,
    get_admin_slot_type_keyboard,
    get_admin_speaker_list_keyboard,
    get_admin_edit_talk_keyboard,
    get_presentation_keyboard
)
from states.states import (
    AdminState,
    StartState,
    AdminAddUserState,
    AdminAddAdminState,
    AdminEditTalkState
)
from utils.text_constants import (
    PAYMENT_MESSAGE,
    PAYMENT_CONFIRMATION_ERROR,
    KEYBOARD_PAYMENT_CONFIRMED,
    COMMENTS_REQUEST
)

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize router and bot
router = Router()
bot = Bot(token=BOT_TOKEN)

# Admin command handler
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Handle /admin command."""
    user_id = message.from_user.id

    # Check if user is admin
    if not await is_admin(user_id):
        await message.answer("У тебя нет прав администратора.")
        return

    # Set state to waiting for admin action
    await state.set_state(AdminState.waiting_for_action)

    # Send admin menu
    await message.answer(
        "🔧 Админ-панель:",
        reply_markup=get_admin_keyboard()
    )

# Admin stats handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_stats")
async def process_admin_stats(callback: CallbackQuery, state: FSMContext):
    """Handle admin stats button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.delete()
        await callback.message.answer(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="stats")

    # Send message with events
    await callback.message.delete()
    await callback.message.answer(
        "Выбери мероприятие:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin event selection handler
@router.callback_query(AdminState.waiting_for_event, F.data.startswith("admin_event_"))
async def process_admin_event_selection(callback: CallbackQuery, state: FSMContext):
    """Handle admin event selection."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[2])

    # Get the action from state data
    data = await state.get_data()
    action = data.get("action", "stats")

    if action == "stats":
        # Get event statistics
        stats = await get_event_statistics(event_id)

        if not stats:
            # Reset state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)
            await callback.message.edit_text(
                "Не удалось получить статистику.",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()
            return

        # Prepare message text
        message_text = (
            f"Статистика по {stats['event']['title']} — {stats['event']['date']}:\n\n"
            f"🔹 Спикеров: {stats['speakers']['active']} / {stats['speakers']['max']}\n"
            f"🔹 Слушателей: {stats['participants']['active']} / {stats['participants']['max']}\n"
            f"🔹 В списке ожидания:\n"
            f"   Спикеры: {stats['speakers']['waitlist']}\n"
            f"   Слушатели: {stats['participants']['waitlist']}\n"
        )

        # Reset state to waiting for admin action
        await state.set_state(AdminState.waiting_for_action)

        # Send message with statistics
        await callback.message.edit_text(
            message_text,
            reply_markup=get_admin_keyboard()
        )

    elif action == "view_participants":
        # Get participants for the event
        participants = await get_event_participants(event_id)

        if not participants:
            # Reset state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)
            await callback.message.edit_text(
                "На это мероприятие еще нет зарегистрированных слушателей.",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()
            return

        # Prepare message text
        message_text = f"Слушатели мероприятия (всего: {len(participants)}):\n\n"

        for i, participant in enumerate(participants, 1):
            message_text += f"{i}. {participant['first_name']} {participant['last_name']}\n"
            if participant['comments']:
                message_text += f"   Комментарий: {participant['comments']}\n"

        # Reset state to waiting for admin action
        await state.set_state(AdminState.waiting_for_action)

        # Send message with participants
        await callback.message.edit_text(
            message_text,
            reply_markup=get_admin_keyboard()
        )

    elif action == "view_speakers":
        # Get speakers for the event
        speakers = await get_event_speakers(event_id)

        if not speakers:
            # Reset state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)
            await callback.message.edit_text(
                "На это мероприятие еще нет зарегистрированных спикеров.",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()
            return

        # Prepare message text
        message_text = f"Спикеры мероприятия (всего: {len(speakers)}):\n\n"

        for i, speaker in enumerate(speakers, 1):
            message_text += f"{i}. {speaker['first_name']} {speaker['last_name']}\n"
            message_text += f"   Тема: {speaker['topic']}\n"
            if speaker['description']:
                message_text += f"   Описание: {speaker['description']}\n"
            message_text += f"   Слайды: {'Да' if speaker['has_presentation'] else 'Нет'}\n"
            if speaker['comments']:
                message_text += f"   Комментарий: {speaker['comments']}\n"
            message_text += "\n"

        # Reset state to waiting for admin action
        await state.set_state(AdminState.waiting_for_action)

        # Send message with speakers
        await callback.message.edit_text(
            message_text,
            reply_markup=get_admin_keyboard()
        )

    elif action == "message_all":
        # Store event_id in state data
        await state.update_data(event_id=event_id)

        # Set state to waiting for message
        await state.set_state(AdminState.waiting_for_message)

        # Ask for message
        await callback.message.edit_text(
            "Введи сообщение, которое хочешь отправить всем слушателям и спикерам этого мероприятия:",
            reply_markup=None
        )

    elif action == "remove_user":
        # Store event_id in state data
        await state.update_data(event_id=event_id)

        # Set state to waiting for role
        await state.set_state(AdminState.waiting_for_role)

        # Send message with role selection
        await callback.message.edit_text(
            "Выбери категорию слушателей:",
            reply_markup=get_admin_role_keyboard(event_id)
        )

    elif action == "change_slots":
        # Store event_id in state data
        await state.update_data(event_id=event_id)

        # Get event statistics to show current slots
        stats = await get_event_statistics(event_id)

        if not stats:
            # Reset state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)
            await callback.message.edit_text(
                "Не удалось получить информацию о мероприятии.",
                reply_markup=get_admin_keyboard()
            )
            await callback.answer()
            return

        # Set state to waiting for slot type
        await state.set_state(AdminState.waiting_for_slot_type)

        # Prepare message text with current slots
        message_text = (
            f"Текущее количество мест для {stats['event']['title']} — {stats['event']['date']}:\n\n"
            f"🎤 Спикеры: {stats['speakers']['active']} / {stats['speakers']['max']} (в ожидании: {stats['speakers']['waitlist']})\n"
            f"🙋‍♀️ Слушатели: {stats['participants']['active']} / {stats['participants']['max']} (в ожидании: {stats['participants']['waitlist']})\n\n"
            f"Выбери, для кого хочешь изменить количество мест:"
        )

        # Send message with slot type selection
        await callback.message.edit_text(
            message_text,
            reply_markup=get_admin_slot_type_keyboard(event_id)
        )

    await callback.answer()

# Admin role selection handler
@router.callback_query(AdminState.waiting_for_role, F.data.startswith("admin_role_"))
async def process_admin_role_selection(callback: CallbackQuery, state: FSMContext):
    """Handle admin role selection."""
    # Extract event_id and role from callback data
    parts = callback.data.split("_")
    event_id = int(parts[2])
    role = parts[3]

    # Store event_id and role in state data
    await state.update_data(event_id=event_id, role=role)

    # Get users based on role
    if role == "speaker":
        users = await get_event_speakers(event_id)
    elif role == "participant":
        users = await get_event_participants(event_id)
    elif role == "all":
        speakers = await get_event_speakers(event_id)
        participants = await get_event_participants(event_id)
        users = speakers + participants
    else:
        users = []

    if not users:
        await callback.message.edit_text(
            "Нет пользователей в выбранной категории.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for user
    await state.set_state(AdminState.waiting_for_user)

    # Send message with user list
    await callback.message.edit_text(
        "Выбери пользователя для удаления:",
        reply_markup=get_admin_user_list_keyboard(users, event_id, role, "remove")
    )

    await callback.answer()

# Admin user selection handler for removal
@router.callback_query(AdminState.waiting_for_user, F.data.startswith("admin_user_remove_"))
async def process_admin_user_removal(callback: CallbackQuery, state: FSMContext):
    """Handle admin user selection for removal."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[3])

    # Store registration_id in state data
    await state.update_data(registration_id=registration_id)

    # Set state to confirmation
    await state.set_state(AdminState.confirmation)

    # Ask for confirmation
    await callback.message.edit_text(
        "Ты уверен, что хочешь удалить этого пользователя?",
        reply_markup=get_admin_confirmation_keyboard()
    )

    await callback.answer()


# Admin message input handler
@router.message(AdminState.waiting_for_message)
async def process_admin_message_input(message: Message, state: FSMContext):
    """Handle admin message input."""
    # Get message text
    message_text = message.text

    # Get event_id from state data
    data = await state.get_data()
    event_id = data.get("event_id")

    if not event_id:
        await message.answer(
            "Произошла ошибка. Попробуй еще раз.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Store message text in state data
    await state.update_data(message_text=message_text)

    # Set state to confirmation
    await state.set_state(AdminState.confirmation)

    # Ask for confirmation
    await message.answer(
        f"Ты собираешься отправить следующее сообщение всем слушателям и спикерам:\n\n"
        f"{message_text}\n\n"
        f"Подтверждаешь отправку?",
        reply_markup=get_admin_confirmation_keyboard()
    )

# Admin confirmation handler
@router.callback_query(F.data == "admin_confirm")
async def process_admin_confirmation(callback: CallbackQuery, state: FSMContext):
    """Handle admin confirmation."""
    # Get current state
    current_state = await state.get_state()

    # Get data from state
    data = await state.get_data()

    if current_state == AdminState.confirmation:
        # Check if this is a message confirmation, a remove user confirmation, or a slot change confirmation
        if "message_text" in data:
            # This is a message confirmation
            event_id = data.get("event_id")
            message_text = data.get("message_text")

            if not event_id or not message_text:
                await callback.message.edit_text(
                    "Произошла ошибка. Попробуй еще раз.",
                    reply_markup=get_admin_keyboard()
                )
                await state.set_state(AdminState.waiting_for_action)
                await callback.answer()
                return

            # Get participants and speakers
            participants = await get_event_participants(event_id)
            speakers = await get_event_speakers(event_id)

            # Combine participants and speakers
            users = participants + speakers

            # Send message to all users
            sent_count = 0
            for user in users:
                try:
                    await bot.send_message(user["user_id"], message_text)
                    sent_count += 1
                except Exception as e:
                    log_exception(
                        exception=e,
                        context={
                            "message_text": message_text,
                            "user": user
                        },
                        user_id=user["user_id"],
                        event_id=event_id,
                        message=f"Failed to send message to user {user['user_id']}"
                    )

            # Set state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)

            # Send confirmation
            await callback.message.edit_text(
                f"Сообщение отправлено {sent_count} из {len(users)} пользователей.",
                reply_markup=get_admin_keyboard()
            )

        elif "registration_id" in data:
            # This is a remove user confirmation
            registration_id = data.get("registration_id")

            if not registration_id:
                await callback.message.edit_text(
                    "Произошла ошибка. Попробуй еще раз.",
                    reply_markup=get_admin_keyboard()
                )
                await state.set_state(AdminState.waiting_for_action)
                await callback.answer()
                return

            try:
                # Get registration details before cancelling
                registration = await get_registration(registration_id)
                if registration:
                    # Cancel the registration
                    await cancel_registration(registration_id)

                    # Send notification to admin chat
                    user_info = {
                        "first_name": registration["first_name"],
                        "last_name": registration["last_name"],
                        "topic": registration["topic"] if "topic" in registration else None
                    }
                    await send_admin_notification(
                        callback.bot,
                        "cancellation",
                        registration["event_id"],
                        user_info,
                        registration["role"],
                        "Удален администратором"
                    )

                    # Check if there's anyone on the waitlist for this event and role
                    from database.db import get_next_from_waitlist
                    from utils.notifications import send_waitlist_notification

                    # Get the next person from the waitlist
                    next_waitlist = await get_next_from_waitlist(registration["event_id"], registration["role"])

                    # Check if there are available slots after cancellation
                    has_slots = await has_available_slots(registration["event_id"], registration["role"])

                    # If there's someone on the waitlist and there are available slots, send them a notification
                    if next_waitlist and has_slots:
                        await send_waitlist_notification(
                            callback.bot,
                            next_waitlist["user_id"],
                            next_waitlist["id"],
                            registration["event_id"],
                            registration["role"]
                        )
                        logger.info(f"Sent waitlist notification to user {next_waitlist['user_id']} after admin removal")
                else:
                    # Registration not found
                    logger.error(f"Registration {registration_id} not found")

                # Set state to waiting for admin action
                await state.set_state(AdminState.waiting_for_action)

                # Send confirmation
                await callback.message.edit_text(
                    "Пользователь успешно удален.",
                    reply_markup=get_admin_keyboard()
                )
            except Exception as e:
                # Get data from state for context
                state_data = await state.get_data()

                # Log the exception with context
                log_exception(
                    exception=e,
                    context={
                        "registration_id": registration_id,
                        "registration": registration,
                        "state_data": state_data
                    },
                    user_id=callback.from_user.id if callback.from_user else None,
                    event_id=registration.get("event_id") if registration else None,
                    message="Failed to remove user"
                )

                # Set state to waiting for admin action
                await state.set_state(AdminState.waiting_for_action)

                # Send error message
                await callback.message.edit_text(
                    f"Не удалось удалить пользователя: {e}",
                    reply_markup=get_admin_keyboard()
                )

        elif "slot_count" in data and "slot_type" in data and "event_id" in data:
            # This is a slot change confirmation
            event_id = data.get("event_id")
            slot_type = data.get("slot_type")
            slot_count = data.get("slot_count")

            if not event_id or not slot_type or not slot_count:
                await callback.message.edit_text(
                    "Произошла ошибка. Попробуй еще раз.",
                    reply_markup=get_admin_keyboard()
                )
                await state.set_state(AdminState.waiting_for_action)
                await callback.answer()
                return

            try:
                # Update the event slots
                from database.db import update_event_slots

                # Set the appropriate parameter based on slot_type
                max_speakers = slot_count if slot_type == "speaker" else None
                max_participants = slot_count if slot_type == "participant" else None

                # Update the slots
                success = await update_event_slots(event_id, max_speakers, max_participants)

                if not success:
                    raise Exception("Failed to update event slots")

                # Get event statistics after update
                stats = await get_event_statistics(event_id)

                if not stats:
                    raise Exception("Failed to get event statistics after update")

                # Check if there are people on the waitlist who can now be notified
                from database.db import get_event_waitlist
                from utils.notifications import send_waitlist_notification

                # Get the role for waitlist queries
                role = "speaker" if slot_type == "speaker" else "participant"

                # Get the waitlist for this event and role
                waitlist = await get_event_waitlist(event_id, role)

                # Count how many people we can notify (new slots - active registrations)
                if role == "speaker":
                    available_slots = stats['speakers']['max'] - stats['speakers']['active']
                else:
                    available_slots = stats['participants']['max'] - stats['participants']['active']

                # Notify people on the waitlist if there are available slots
                notified_count = 0
                for i, entry in enumerate(waitlist):
                    if i < available_slots and entry["status"] == "active":
                        await send_waitlist_notification(
                            callback.bot,
                            entry["user_id"],
                            entry["id"],
                            event_id,
                            role
                        )
                        notified_count += 1
                        logger.info(f"Sent waitlist notification to user {entry['user_id']} after slot increase")

                # Set state to waiting for admin action
                await state.set_state(AdminState.waiting_for_action)

                # Prepare confirmation message
                role_text = "спикеров" if role == "speaker" else "слушателей"
                message_text = (
                    f"Количество мест для {role_text} успешно изменено на {slot_count}.\n"
                )

                if notified_count > 0:
                    message_text += f"Отправлено {notified_count} уведомлений пользователям из списка ожидания."

                # Send confirmation
                await callback.message.edit_text(
                    message_text,
                    reply_markup=get_admin_keyboard()
                )
            except Exception as e:
                # Get data from state for context
                state_data = await state.get_data()

                # Log the exception with context
                log_exception(
                    exception=e,
                    context={
                        "event_id": event_id,
                        "slot_type": slot_type,
                        "slot_count": slot_count,
                        "state_data": state_data
                    },
                    user_id=callback.from_user.id if callback.from_user else None,
                    event_id=event_id,
                    message="Failed to update slots"
                )

                # Set state to waiting for admin action
                await state.set_state(AdminState.waiting_for_action)

                # Send error message
                await callback.message.edit_text(
                    f"Не удалось изменить количество мест: {e}",
                    reply_markup=get_admin_keyboard()
                )

    elif current_state == AdminAddAdminState.confirmation:
        # This is an add admin confirmation
        new_admin_id = data.get("new_admin_id")

        if not new_admin_id:
            await callback.message.edit_text(
                "Произошла ошибка. Попробуй еще раз.",
                reply_markup=get_admin_keyboard()
            )
            await state.set_state(AdminState.waiting_for_action)
            await callback.answer()
            return

        try:
            # Add the new admin
            await add_admin(new_admin_id)

            # Set state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)

            # Send confirmation
            await callback.message.edit_text(
                f"Пользователь с ID {new_admin_id} успешно добавлен как администратор.",
                reply_markup=get_admin_keyboard()
            )
        except Exception as e:
            # Log the exception with context
            log_exception(
                exception=e,
                context={
                    "new_admin_id": new_admin_id,
                    "state_data": data
                },
                user_id=callback.from_user.id if callback.from_user else None,
                message="Failed to add admin"
            )

            # Set state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)

            # Send error message
            await callback.message.edit_text(
                f"Не удалось добавить администратора: {e}",
                reply_markup=get_admin_keyboard()
            )

    elif current_state == AdminAddUserState.confirmation:
        # This is an add user confirmation
        event_id = data.get("event_id")
        role = data.get("role")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        username = data.get("username")
        topic = data.get("topic")
        description = data.get("description")
        has_presentation = data.get("has_presentation", False)
        comments = data.get("comments")

        # Generate a random user_id for the manually added user
        user_id = int(f"999{event_id}{int(datetime.now().timestamp())}")

        try:
            # Register the user
            await register_user(
                event_id=event_id,
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                role=role,
                status="active",
                topic=topic,
                description=description,
                has_presentation=has_presentation,
                comments=comments,
                username=username
            )

            # Send notification to admin chat
            user_info = {
                "first_name": first_name,
                "last_name": last_name,
                "topic": topic
            }
            await send_admin_notification(
                callback.bot,
                "registration",
                event_id,
                user_info,
                role,
                "Добавлен администратором"
            )

            # Set state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)

            # Send confirmation
            role_text = 'Спикер' if role == 'speaker' else 'Слушатель'
            await callback.message.edit_text(
                f"{role_text} {first_name} {last_name} успешно добавлен.",
                reply_markup=get_admin_keyboard()
            )
        except Exception as e:
            # Get data from state for context
            state_data = await state.get_data()

            # Log the exception with context
            log_exception(
                exception=e,
                context={
                    "event_id": event_id,
                    "role": role,
                    "first_name": first_name,
                    "last_name": last_name,
                    "topic": topic,
                    "description": description,
                    "has_presentation": has_presentation,
                    "comments": comments,
                    "user_id": user_id,
                    "state_data": state_data
                },
                user_id=callback.from_user.id if callback.from_user else None,
                event_id=event_id,
                message="Failed to add user"
            )

            # Set state to waiting for admin action
            await state.set_state(AdminState.waiting_for_action)

            # Send error message
            await callback.message.edit_text(
                f"Не удалось добавить слушателя: {e}",
                reply_markup=get_admin_keyboard()
            )

    await callback.answer()

# Admin view participants handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_view_participants")
async def process_admin_view_participants(callback: CallbackQuery, state: FSMContext):
    """Handle admin view participants button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="view_participants")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin view speakers handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_view_speakers")
async def process_admin_view_speakers(callback: CallbackQuery, state: FSMContext):
    """Handle admin view speakers button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="view_speakers")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin message all handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_message_all")
async def process_admin_message_all(callback: CallbackQuery, state: FSMContext):
    """Handle admin message all button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="message_all")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие, слушателям которого хочешь отправить сообщение:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin add speaker handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_add_speaker")
async def process_admin_add_speaker(callback: CallbackQuery, state: FSMContext):
    """Handle admin add speaker button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminAddUserState.waiting_for_event)

    # Store role as speaker
    await state.update_data(role="speaker")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие, на которое хочешь добавить спикера:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin add user handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_add_user")
async def process_admin_add_user(callback: CallbackQuery, state: FSMContext):
    """Handle admin add user button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminAddUserState.waiting_for_event)

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие, на которое хочешь добавить слушателя:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin remove user handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_remove_user")
async def process_admin_remove_user(callback: CallbackQuery, state: FSMContext):
    """Handle admin remove user button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="remove_user")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие, из которого хочешь удалить слушателя:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin change slots handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_change_slots")
async def process_admin_change_slots(callback: CallbackQuery, state: FSMContext):
    """Handle admin change slots button click."""
    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="change_slots")

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие, для которого хочешь изменить количество мест:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Back to admin handler
@router.callback_query(F.data == "back_to_admin")
async def process_back_to_admin(callback: CallbackQuery, state: FSMContext):
    """Handle back to admin button click."""
    # Get current state
    current_state = await state.get_state()

    # Set state to waiting for admin action
    await state.set_state(AdminState.waiting_for_action)

    # Send admin menu
    await callback.message.edit_text(
        "🔧 Админ-панель:",
        reply_markup=get_admin_keyboard()
    )

    await callback.answer()

# Admin add user event selection handler
@router.callback_query(AdminAddUserState.waiting_for_event, F.data.startswith("admin_event_"))
async def process_admin_add_user_event(callback: CallbackQuery, state: FSMContext):
    """Handle admin add user event selection."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[2])

    # Store event_id in state data
    await state.update_data(event_id=event_id)

    # Get data from state
    data = await state.get_data()
    role = data.get("role")

    # If role is already set (from admin_add_speaker), skip role selection
    if role:
        # Set state to waiting for first name
        await state.set_state(AdminAddUserState.waiting_for_first_name)

        # Ask for first name
        await callback.message.edit_text(
            "Введи имя нового слушателя:",
            reply_markup=None
        )
    else:
        # Set state to waiting for role
        await state.set_state(AdminAddUserState.waiting_for_role)

        # Send message with role selection
        await callback.message.edit_text(
            "Выбери роль для нового слушателя:",
            reply_markup=get_admin_role_keyboard(event_id)
        )

    await callback.answer()

# Admin add user role selection handler
@router.callback_query(AdminAddUserState.waiting_for_role, F.data.startswith("admin_role_"))
async def process_admin_add_user_role(callback: CallbackQuery, state: FSMContext):
    """Handle admin add user role selection."""
    # Extract role from callback data
    role = callback.data.split("_")[3]

    # Store role in state data
    await state.update_data(role=role)

    # Set state to waiting for first name
    await state.set_state(AdminAddUserState.waiting_for_first_name)

    # Ask for first name
    await callback.message.edit_text(
        "Введи имя нового слушателя:",
        reply_markup=None
    )

    await callback.answer()

# Admin add user first name handler
@router.message(AdminAddUserState.waiting_for_first_name)
async def process_admin_add_user_first_name(message: Message, state: FSMContext):
    """Handle admin add user first name input."""
    # Get first name
    first_name = message.text

    # Store first name in state data
    await state.update_data(first_name=first_name)

    # Set state to waiting for last name
    await state.set_state(AdminAddUserState.waiting_for_last_name)

    # Ask for last name
    await message.answer("Введи фамилию нового слушателя:")

# Admin add user last name handler
@router.message(AdminAddUserState.waiting_for_last_name)
async def process_admin_add_user_last_name(message: Message, state: FSMContext):
    """Handle admin add user last name input."""
    # Get last name
    last_name = message.text

    # Store last name in state data
    await state.update_data(last_name=last_name)

    # Set state to waiting for username
    await state.set_state(AdminAddUserState.waiting_for_username)

    # Ask for username
    await message.answer("Введи username в Telegram (с символом @ в начале) или '-' если его нет:")

# Admin add user username handler
@router.message(AdminAddUserState.waiting_for_username)
async def process_admin_add_user_username(message: Message, state: FSMContext):
    """Handle admin add user username input."""
    # Get username
    username = message.text

    # Store username in state data (None if '-' was entered)
    await state.update_data(username=None if username == '-' else username)

    # Get data from state
    data = await state.get_data()
    role = data.get("role")

    if role == "speaker":
        # Set state to waiting for topic
        await state.set_state(AdminAddUserState.waiting_for_topic)

        # Ask for topic
        await message.answer("Введи тему доклада:")
    else:
        # Set state to waiting for comments
        await state.set_state(AdminAddUserState.waiting_for_comments)

        # Ask for comments
        await message.answer(COMMENTS_REQUEST)

# Admin add user topic handler
@router.message(AdminAddUserState.waiting_for_topic)
async def process_admin_add_user_topic(message: Message, state: FSMContext):
    """Handle admin add user topic input."""
    # Get topic
    topic = message.text

    # Store topic in state data
    await state.update_data(topic=topic)

    # Set state to waiting for description
    await state.set_state(AdminAddUserState.waiting_for_description)

    # Ask for description
    await message.answer("Введи описание доклада (или просто отправь '-', если его нет):")

# Admin add user description handler
@router.message(AdminAddUserState.waiting_for_description)
async def process_admin_add_user_description(message: Message, state: FSMContext):
    """Handle admin add user description input."""
    # Get description
    description = message.text

    # Store description in state data
    await state.update_data(description=description if description != "-" else None)

    # Set state to waiting for presentation
    await state.set_state(AdminAddUserState.waiting_for_presentation)

    # Ask for presentation
    await message.answer("Будут ли слайды? (да/нет)")

# Admin add user presentation handler
@router.message(AdminAddUserState.waiting_for_presentation)
async def process_admin_add_user_presentation(message: Message, state: FSMContext):
    """Handle admin add user presentation input."""
    # Get presentation
    has_presentation = message.text.lower() in ["да", "yes", "y", "+"]

    # Store presentation in state data
    await state.update_data(has_presentation=has_presentation)

    # Set state to waiting for payment
    await state.set_state(AdminAddUserState.waiting_for_payment)

    # Ask for payment
    payment_message = PAYMENT_MESSAGE.format(REVOLUT_DONATION_URL)

    await message.answer(
        payment_message,
        reply_markup=get_payment_confirmation_keyboard(),
        parse_mode="HTML"
    )

# Admin add user payment confirmation handler
@router.message(AdminAddUserState.waiting_for_payment)
async def process_admin_add_user_payment(message: Message, state: FSMContext):
    """Handle admin add user payment confirmation."""
    confirmation = message.text.strip()

    # Validate confirmation
    if confirmation != KEYBOARD_PAYMENT_CONFIRMED:
        await message.answer(
            PAYMENT_CONFIRMATION_ERROR,
            reply_markup=get_payment_confirmation_keyboard()
        )
        return

    # Set state to waiting for comments
    await state.set_state(AdminAddUserState.waiting_for_comments)

    # Ask for comments
    await message.answer(COMMENTS_REQUEST)

# Admin add user comments handler
@router.message(AdminAddUserState.waiting_for_comments)
async def process_admin_add_user_comments(message: Message, state: FSMContext):
    """Handle admin add user comments input."""
    # Get comments
    comments = message.text

    # Store comments in state data
    await state.update_data(comments=comments if comments != "-" else None)

    # Get data from state
    data = await state.get_data()
    event_id = data.get("event_id")
    role = data.get("role")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    username = data.get("username")
    topic = data.get("topic")
    description = data.get("description")
    has_presentation = data.get("has_presentation", False)
    comments = data.get("comments")

    # Set state to confirmation
    await state.set_state(AdminAddUserState.confirmation)

    # Prepare confirmation message
    role_text = 'Спикер' if role == 'speaker' else 'Слушатель'
    message_text = (
        f"Ты собираешься добавить нового {role_text.lower()}а:\n\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Username: {username or '-'}\n"
        f"Роль: {role_text}\n"
    )

    if role == "speaker":
        message_text += (
            f"Тема: {topic}\n"
            f"Описание: {description or '-'}\n"
            f"Презентация: {'Да' if has_presentation else 'Нет'}\n"
        )

    message_text += f"Комментарии: {comments or '-'}\n\n"
    message_text += "Подтверждаешь добавление?"

    # Ask for confirmation
    await message.answer(
        message_text,
        reply_markup=get_admin_confirmation_keyboard()
    )


# Admin slot type selection handler
@router.callback_query(AdminState.waiting_for_slot_type, F.data.startswith("admin_slot_type_"))
async def process_admin_slot_type_selection(callback: CallbackQuery, state: FSMContext):
    """Handle admin slot type selection."""
    # Extract event_id and slot_type from callback data
    parts = callback.data.split("_")
    event_id = int(parts[3])
    slot_type = parts[4]  # 'speaker' or 'participant'

    # Store event_id and slot_type in state data
    await state.update_data(event_id=event_id, slot_type=slot_type)

    # Get event statistics to show current slots
    stats = await get_event_statistics(event_id)

    if not stats:
        # Reset state to waiting for admin action
        await state.set_state(AdminState.waiting_for_action)
        await callback.message.edit_text(
            "Не удалось получить информацию о мероприятии.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Get current slot count and active registrations
    if slot_type == "speaker":
        current_slots = stats['speakers']['max']
        active_count = stats['speakers']['active']
        waitlist_count = stats['speakers']['waitlist']
        role_text = "спикеров"
    else:  # participant
        current_slots = stats['participants']['max']
        active_count = stats['participants']['active']
        waitlist_count = stats['participants']['waitlist']
        role_text = "слушателей"

    # Set state to waiting for slot count
    await state.set_state(AdminState.waiting_for_slot_count)

    # Prepare message text
    message_text = (
        f"Текущее количество мест для {role_text}: {current_slots}\n"
        f"Активных регистраций: {active_count}\n"
        f"В списке ожидания: {waitlist_count}\n\n"
        f"Введи новое количество мест для {role_text}:"
    )

    # Send message asking for new slot count
    await callback.message.edit_text(
        message_text,
        reply_markup=None
    )

    await callback.answer()

# Admin slot count input handler
@router.message(AdminState.waiting_for_slot_count)
async def process_admin_slot_count_input(message: Message, state: FSMContext):
    """Handle admin slot count input."""
    # Get slot count
    try:
        slot_count = int(message.text.strip())
        if slot_count < 0:
            raise ValueError("Slot count must be positive")
    except ValueError:
        await message.answer(
            "Пожалуйста, введи положительное целое число.",
            reply_markup=None
        )
        return

    # Get data from state
    data = await state.get_data()
    event_id = data.get("event_id")
    slot_type = data.get("slot_type")

    if not event_id or not slot_type:
        await message.answer(
            "Произошла ошибка. Попробуй еще раз.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Get event statistics
    stats = await get_event_statistics(event_id)

    if not stats:
        await message.answer(
            "Не удалось получить информацию о мероприятии.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Get current values
    if slot_type == "speaker":
        current_slots = stats['speakers']['max']
        active_count = stats['speakers']['active']
        role_text = "спикеров"
    else:  # participant
        current_slots = stats['participants']['max']
        active_count = stats['participants']['active']
        role_text = "слушателей"

    # Check if new slot count is less than active registrations
    if slot_count < active_count:
        await message.answer(
            f"Новое количество мест ({slot_count}) меньше, чем количество активных регистраций ({active_count}).\n"
            f"Пожалуйста, введи число не меньше {active_count}.",
            reply_markup=None
        )
        return

    # Store slot_count in state data
    await state.update_data(slot_count=slot_count)

    # Set state to confirmation
    await state.set_state(AdminState.confirmation)

    # Prepare confirmation message
    message_text = (
        f"Ты собираешься изменить количество мест для {role_text} с {current_slots} на {slot_count}.\n\n"
        f"Подтверждаешь изменение?"
    )

    # Ask for confirmation
    await message.answer(
        message_text,
        reply_markup=get_admin_confirmation_keyboard()
    )

# Back to admin events handler
@router.callback_query(F.data == "back_to_admin_events")
async def process_back_to_admin_events(callback: CallbackQuery, state: FSMContext):
    """Handle back to admin events button click."""
    # Get data from state
    data = await state.get_data()
    action = data.get("action", "stats")

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)

    # Get open events
    events = await get_open_events()

    # Send message with events
    await callback.message.edit_text(
        "Выбери мероприятие:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Back to admin role handler
@router.callback_query(F.data.startswith("back_to_admin_role_"))
async def process_back_to_admin_role(callback: CallbackQuery, state: FSMContext):
    """Handle back to admin role button click."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[4])

    # Store event_id in state data
    await state.update_data(event_id=event_id)

    # Set state to waiting for role
    await state.set_state(AdminState.waiting_for_role)

    # Send message with role selection
    await callback.message.edit_text(
        "Выбери категорию слушателей:",
        reply_markup=get_admin_role_keyboard(event_id)
    )

    await callback.answer()

# Back to start handler
@router.callback_query(F.data == "back_to_start")
async def process_back_to_start(callback: CallbackQuery, state: FSMContext):
    """Handle back to start button click."""
    # Clear state
    await state.clear()

    # Set state to waiting for action
    await state.set_state(StartState.waiting_for_action)

    # Send start message
    await callback.message.edit_text(
        "Привет! Я бот Larnaka Roof Talks 🌇\n\n"
        "Что хочешь сделать?",
        reply_markup=get_start_keyboard()
    )

    await callback.answer()

# Admin edit talk handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_edit_talk")
async def process_admin_edit_talk(callback: CallbackQuery, state: FSMContext):
    """Handle admin edit talk button click."""
    user_id = callback.from_user.id

    # Check if user is admin
    if not await is_admin(user_id):
        await callback.message.answer("У тебя нет прав администратора.")
        await callback.answer()
        return

    # Get open events
    events = await get_open_events()

    if not events:
        await callback.message.edit_text(
            "Нет активных мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminEditTalkState.waiting_for_event)

    # Show events
    await callback.message.edit_text(
        "Выбери мероприятие, для которого хочешь отредактировать доклад:",
        reply_markup=get_admin_events_keyboard(events)
    )

    await callback.answer()

# Admin add admin handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_add_admin")
async def process_admin_add_admin(callback: CallbackQuery, state: FSMContext):
    """Handle admin add admin button click."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    user_id = callback.from_user.id

    # Check if user is admin
    if not await is_admin(user_id):
        await callback.message.answer("У тебя нет прав администратора.")
        await callback.answer()
        return

    # Set state to waiting for user ID
    await state.set_state(AdminAddAdminState.waiting_for_user_id)

    # Ask for user ID
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
    ])

    await callback.message.edit_text(
        "Введи ID пользователя, которого хочешь сделать администратором:\n\n"
        "ID можно узнать, например, через бота @userinfobot",
        reply_markup=keyboard
    )

    await callback.answer()

# Admin add admin user ID handler
@router.message(AdminAddAdminState.waiting_for_user_id)
async def process_admin_add_admin_user_id(message: Message, state: FSMContext):
    """Handle admin add admin user ID input."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # Get user ID
    try:
        new_admin_id = int(message.text.strip())
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
        ])

        await message.answer(
            "Пожалуйста, введи корректный ID пользователя (только цифры).",
            reply_markup=keyboard
        )
        return

    # Store user ID in state data
    await state.update_data(new_admin_id=new_admin_id)

    # Check if user is already an admin
    if await is_admin(new_admin_id):
        await message.answer(
            "Этот пользователь уже является администратором.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Set state to confirmation
    await state.set_state(AdminAddAdminState.confirmation)

    # Ask for confirmation
    await message.answer(
        f"Ты собираешься добавить пользователя с ID {new_admin_id} в качестве администратора.\n\n"
        f"Подтверждаешь добавление?",
        reply_markup=get_admin_confirmation_keyboard()
    )

# Admin edit talk event selection handler
@router.callback_query(AdminEditTalkState.waiting_for_event, F.data.startswith("admin_event_"))
async def process_admin_edit_talk_event(callback: CallbackQuery, state: FSMContext):
    """Handle event selection for admin talk editing."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[2])

    # Get event details
    event = await get_event(event_id)

    if not event:
        await callback.message.edit_text(
            "Мероприятие не найдено.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Get speakers for this event
    speakers = await get_event_speakers(event_id)

    if not speakers:
        await callback.message.edit_text(
            f"Для мероприятия \"{event['title']}\" нет спикеров.",
            reply_markup=get_admin_events_keyboard(await get_open_events())
        )
        await callback.answer()
        return

    # Store event_id in state data
    await state.update_data(event_id=event_id)

    # Set state to waiting for speaker
    await state.set_state(AdminEditTalkState.waiting_for_speaker)

    # Show speakers
    await callback.message.edit_text(
        f"Выбери спикера, чей доклад хочешь отредактировать для мероприятия \"{event['title']}\":",
        reply_markup=get_admin_speaker_list_keyboard(speakers, event_id)
    )

    await callback.answer()

# Admin edit talk speaker selection handler
@router.callback_query(AdminEditTalkState.waiting_for_speaker, F.data.startswith("admin_edit_speaker_"))
async def process_admin_edit_talk_speaker(callback: CallbackQuery, state: FSMContext):
    """Handle speaker selection for admin talk editing."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[3])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Get event details
    event = await get_event(registration["event_id"])

    # Store registration_id in state data
    await state.update_data(registration_id=registration_id)

    # Set state to waiting for field
    await state.set_state(AdminEditTalkState.waiting_for_field)

    # Show edit options
    await callback.message.edit_text(
        f"Редактирование доклада \"{registration['topic']}\" для спикера {registration['first_name']} {registration['last_name']}.\n"
        f"Выбери, что ты хочешь изменить:",
        reply_markup=get_admin_edit_talk_keyboard(registration_id)
    )

    await callback.answer()

# Admin edit talk topic handler
@router.callback_query(AdminEditTalkState.waiting_for_field, F.data.startswith("admin_edit_topic_"))
async def process_admin_edit_topic(callback: CallbackQuery, state: FSMContext):
    """Handle edit topic button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[3])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Store registration_id in state data
    await state.update_data(registration_id=registration_id)

    # Set state to waiting for topic
    await state.set_state(AdminEditTalkState.waiting_for_topic)

    # Show current topic and ask for new one
    await callback.message.edit_text(
        f"Текущая тема: {registration['topic']}\n\n"
        f"Введи новую тему доклада:",
        reply_markup=None
    )

    await callback.answer()

# Admin edit talk description handler
@router.callback_query(AdminEditTalkState.waiting_for_field, F.data.startswith("admin_edit_description_"))
async def process_admin_edit_description(callback: CallbackQuery, state: FSMContext):
    """Handle edit description button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[3])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Store registration_id in state data
    await state.update_data(registration_id=registration_id)

    # Set state to waiting for description
    await state.set_state(AdminEditTalkState.waiting_for_description)

    # Show current description and ask for new one
    await callback.message.edit_text(
        f"Текущее описание: {registration['description']}\n\n"
        f"Введи новое описание доклада:",
        reply_markup=None
    )

    await callback.answer()

# Admin edit talk presentation handler
@router.callback_query(AdminEditTalkState.waiting_for_field, F.data.startswith("admin_edit_presentation_"))
async def process_admin_edit_presentation(callback: CallbackQuery, state: FSMContext):
    """Handle edit presentation button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[3])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Store registration_id in state data
    await state.update_data(registration_id=registration_id)

    # Set state to waiting for presentation
    await state.set_state(AdminEditTalkState.waiting_for_presentation)

    # Show current presentation status and ask for new one
    current_status = "Да" if registration["has_presentation"] else "Нет"
    await callback.message.edit_text(
        f"Текущий статус презентации: {current_status}\n\n"
        f"Будет ли у спикера презентация?",
        reply_markup=get_presentation_keyboard()
    )

    await callback.answer()

# Process new topic for admin edit
@router.message(AdminEditTalkState.waiting_for_topic)
async def process_admin_new_topic(message: Message, state: FSMContext):
    """Process new topic input from admin."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await message.answer(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Get new topic
    new_topic = message.text.strip()

    # Validate topic
    if not new_topic:
        await message.answer(
            "Тема не может быть пустой. Пожалуйста, введи тему доклада:",
            reply_markup=None
        )
        return

    # Update registration with new topic
    await update_registration(registration_id, topic=new_topic)

    # Get updated registration
    updated_registration = await get_registration(registration_id)

    # Set state to confirmation
    await state.set_state(AdminEditTalkState.confirmation)

    # Show confirmation
    await message.answer(
        f"Тема доклада успешно обновлена!\n\n"
        f"Новая тема: {updated_registration['topic']}\n\n"
        f"Хочешь отредактировать что-то еще?",
        reply_markup=get_admin_edit_talk_keyboard(registration_id)
    )

# Process new description for admin edit
@router.message(AdminEditTalkState.waiting_for_description)
async def process_admin_new_description(message: Message, state: FSMContext):
    """Process new description input from admin."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await message.answer(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        return

    # Get new description
    new_description = message.text.strip()

    # Validate description
    if not new_description:
        await message.answer(
            "Описание не может быть пустым. Пожалуйста, введи описание доклада:",
            reply_markup=None
        )
        return

    # Update registration with new description
    await update_registration(registration_id, description=new_description)

    # Get updated registration
    updated_registration = await get_registration(registration_id)

    # Set state to confirmation
    await state.set_state(AdminEditTalkState.confirmation)

    # Show confirmation
    await message.answer(
        f"Описание доклада успешно обновлено!\n\n"
        f"Новое описание: {updated_registration['description']}\n\n"
        f"Хочешь отредактировать что-то еще?",
        reply_markup=get_admin_edit_talk_keyboard(registration_id)
    )

# Process new presentation status for admin edit
@router.callback_query(AdminEditTalkState.waiting_for_presentation, F.data.startswith("presentation_"))
async def process_admin_new_presentation(callback: CallbackQuery, state: FSMContext):
    """Process new presentation status input from admin."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Get new presentation status
    has_presentation = callback.data == "presentation_yes"

    # Update registration with new presentation status
    await update_registration(registration_id, has_presentation=has_presentation)

    # Get updated registration
    updated_registration = await get_registration(registration_id)

    # Set state to confirmation
    await state.set_state(AdminEditTalkState.confirmation)

    # Show confirmation
    current_status = "Да" if updated_registration["has_presentation"] else "Нет"
    await callback.message.edit_text(
        f"Статус презентации успешно обновлен!\n\n"
        f"Новый статус: {current_status}\n\n"
        f"Хочешь отредактировать что-то еще?",
        reply_markup=get_admin_edit_talk_keyboard(registration_id)
    )

    await callback.answer()

# Back to admin speakers handler
@router.callback_query(F.data == "back_to_admin_speakers")
async def process_back_to_admin_speakers(callback: CallbackQuery, state: FSMContext):
    """Handle back to admin speakers button click."""
    # Get data from state
    data = await state.get_data()
    event_id = data.get("event_id")

    # Get event details
    event = await get_event(event_id)

    if not event:
        await callback.message.edit_text(
            "Мероприятие не найдено.",
            reply_markup=get_admin_keyboard()
        )
        await state.set_state(AdminState.waiting_for_action)
        await callback.answer()
        return

    # Get speakers for this event
    speakers = await get_event_speakers(event_id)

    # Set state to waiting for speaker
    await state.set_state(AdminEditTalkState.waiting_for_speaker)

    # Show speakers
    await callback.message.edit_text(
        f"Выбери спикера, чей доклад хочешь отредактировать для мероприятия \"{event['title']}\":",
        reply_markup=get_admin_speaker_list_keyboard(speakers, event_id)
    )

    await callback.answer()

# Database export handler
@router.callback_query(AdminState.waiting_for_action, F.data == "admin_export_db")
async def process_admin_export_db(callback: CallbackQuery, state: FSMContext):
    """Handle database export button click."""
    user_id = callback.from_user.id

    # Check if user is admin
    if not await is_admin(user_id):
        await callback.message.answer("У тебя нет прав администратора.")
        await callback.answer()
        return

    try:
        # Create FSInputFile from the database file
        db_file = FSInputFile(DB_NAME, filename=DB_NAME)

        # Send the database file to the user
        await callback.message.edit_text("Выгружаю базу данных...")
        await bot.send_document(
            chat_id=user_id,
            document=db_file,
            caption="База данных Roof Talks"
        )

        # Send success message
        await callback.message.answer(
            "База данных успешно выгружена.",
            reply_markup=get_admin_keyboard()
        )

        # Log the export
        logger.info(f"Database exported by admin {user_id}")

    except Exception as e:
        # Log the error
        log_exception(
            exception=e,
            context={"action": "database_export"},
            user_id=user_id,
            message="Error exporting database"
        )

        # Send error message
        await callback.message.answer(
            "Произошла ошибка при выгрузке базы данных. Попробуй еще раз позже.",
            reply_markup=get_admin_keyboard()
        )

    await callback.answer()

# Automatic database export function
async def export_database_auto():
    """Automatically export database to backup chat."""
    try:
        # Create FSInputFile from the database file
        db_file = FSInputFile(DB_NAME, filename=DB_NAME)

        # Get current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Send the database file to the backup chat
        await bot.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=db_file,
            caption=f"Автоматическая выгрузка базы данных Roof Talks\nДата: {current_time}"
        )

        # Log the export
        logger.info(f"Database automatically exported to backup chat {BACKUP_CHAT_ID}")

    except Exception as e:
        # Log the error
        log_exception(
            exception=e,
            context={"action": "automatic_database_export"},
            message="Error automatically exporting database"
        )
