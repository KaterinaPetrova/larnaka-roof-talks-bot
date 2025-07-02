import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import (
    get_registration, 
    update_registration, 
    cancel_registration,
    get_event,
    get_next_from_waitlist,
    update_waitlist_status,
    get_user_registrations,
    get_waitlist_entry,
    register_user
)
from keyboards.keyboards import (
    get_my_events_keyboard, 
    get_edit_talk_keyboard, 
    get_cancel_registration_keyboard,
    get_presentation_keyboard,
    get_start_keyboard
)
from states.states import (
    MyEventsState, 
    EditTalkState, 
    CancelRegistrationState,
    StartState,
    WaitlistNotificationState
)
from utils.validation import can_edit_talk, validate_speaker_data
from utils.notifications import (
    send_talk_update_confirmation,
    send_waitlist_notification,
    send_admin_notification, send_registration_confirmation
)
from config import (
    ROLE_SPEAKER, 
    REG_STATUS_ACTIVE, 
    REG_STATUS_CANCELLED
)
from datetime import datetime
from text_constants import (
    PAYMENT_MESSAGE,
    PAYMENT_CONFIRMATION_ERROR,
    KEYBOARD_PAYMENT_CONFIRMED
)

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize router
router = Router()

# Back to my events handler
@router.callback_query(F.data == "back_to_my_events")
async def process_back_to_my_events(callback: CallbackQuery, state: FSMContext):
    """Handle back to my events button click."""
    user_id = callback.from_user.id

    # Get user's registrations
    registrations = await get_user_registrations(user_id)

    if not registrations:
        await callback.message.delete()
        await callback.message.answer(
            "У тебя пока нет регистраций на мероприятия.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(MyEventsState.waiting_for_event)

    # Send message with registrations
    await callback.message.delete()
    await callback.message.answer(
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

    await callback.answer()

# Waitlist notification handlers
@router.callback_query(F.data.startswith("accept_waitlist_"))
async def process_accept_waitlist(callback: CallbackQuery, state: FSMContext):
    """Handle accept waitlist button click."""
    # Extract waitlist_id from callback data
    waitlist_id = int(callback.data.split("_")[2])

    try:
        # Get waitlist entry
        waitlist_entry = await get_waitlist_entry(waitlist_id)

        if not waitlist_entry:
            await callback.message.delete()
            await callback.message.answer(
                "Ошибка: запись в листе ожидания не найдена.",
                reply_markup=get_start_keyboard()
            )
            await callback.answer()
            return

        # Check if the waitlist entry is still active or notified
        if waitlist_entry["status"] not in ["active", "notified"]:
            await callback.message.delete()
            await callback.message.answer(
                "Это приглашение больше не действительно.",
                reply_markup=get_start_keyboard()
            )
            await callback.answer()
            return

        # Get event details for the confirmation message, passing user_id to filter test events for non-admins
        user_id = callback.from_user.id
        event = await get_event(waitlist_entry["event_id"], user_id)

        # For speakers, register directly without payment
        if waitlist_entry["role"] == ROLE_SPEAKER:
            # Register the user for the event
            await register_user(
                waitlist_entry["event_id"],
                waitlist_entry["user_id"],
                waitlist_entry["first_name"],
                waitlist_entry["last_name"],
                waitlist_entry["role"],
                REG_STATUS_ACTIVE,
                waitlist_entry["topic"],
                waitlist_entry["description"],
                waitlist_entry["has_presentation"],
                waitlist_entry["comments"]
            )

            # Update waitlist status to accepted
            await update_waitlist_status(waitlist_id, "accepted")

            await state.clear()

            await send_registration_confirmation(
                callback.message.bot,
                callback.from_user.id,
                waitlist_entry["event_id"],
                waitlist_entry["role"]
            )


            # Send admin notification
            await send_admin_notification(
                callback.bot,
                "waitlist_accepted",
                waitlist_entry["event_id"],
                {
                    "user_id": waitlist_entry["user_id"],
                    "first_name": waitlist_entry["first_name"],
                    "last_name": waitlist_entry["last_name"]
                },
                waitlist_entry["role"]
            )

            logger.info(f"Speaker {waitlist_entry['user_id']} accepted waitlist spot for event {waitlist_entry['event_id']}")
        else:
            # For participants, show payment step first
            # Store waitlist entry data in state
            await state.update_data(
                waitlist_id=waitlist_id,
                waitlist_entry=waitlist_entry,
                event=event
            )

            # Set state to waiting for payment
            await state.set_state(WaitlistNotificationState.waiting_for_payment)

            # Show payment message
            from config import REVOLUT_DONATION_URL

            # No need to escape special characters for HTML format
            payment_message = PAYMENT_MESSAGE.format(REVOLUT_DONATION_URL)

            from keyboards.keyboards import get_payment_confirmation_keyboard
            await callback.message.edit_text(
                payment_message,
                reply_markup=get_payment_confirmation_keyboard(),
                parse_mode="HTML"
            )

            logger.info(f"Participant {waitlist_entry['user_id']} accepted waitlist spot for event {waitlist_entry['event_id']} - waiting for payment")
    except Exception as e:
        logger.error(f"Error accepting waitlist: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при подтверждении участия. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
            reply_markup=get_start_keyboard()
        )

    await callback.answer()

# Waitlist payment confirmation handlers
@router.message(WaitlistNotificationState.waiting_for_payment)
async def process_waitlist_payment_confirmation(message: Message, state: FSMContext):
    """Handle payment confirmation for waitlist participants (message version)."""
    confirmation = message.text.strip()

    # Validate confirmation
    if confirmation != KEYBOARD_PAYMENT_CONFIRMED:
        from keyboards.keyboards import get_payment_confirmation_keyboard
        await message.answer(
            PAYMENT_CONFIRMATION_ERROR,
            reply_markup=get_payment_confirmation_keyboard()
        )
        return

    try:
        # Get data from state
        data = await state.get_data()
        waitlist_id = data.get("waitlist_id")
        waitlist_entry = data.get("waitlist_entry")
        event = data.get("event")

        if not waitlist_entry or not waitlist_id or not event:
            await message.answer(
                "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
                reply_markup=get_start_keyboard()
            )
            await state.clear()
            return

        # Register the user for the event
        await register_user(
            waitlist_entry["event_id"],
            waitlist_entry["user_id"],
            waitlist_entry["first_name"],
            waitlist_entry["last_name"],
            waitlist_entry["role"],
            REG_STATUS_ACTIVE,
            waitlist_entry["topic"],
            waitlist_entry["description"],
            waitlist_entry["has_presentation"],
            waitlist_entry["comments"]
        )

        # Update waitlist status to accepted
        await update_waitlist_status(waitlist_id, "accepted")

        await send_registration_confirmation(
            message.bot,
            message.from_user.id,
            waitlist_entry["event_id"],
            waitlist_entry["role"]
        )

        await state.clear()

        # Send confirmation message
        await message.answer(
            f"Что хочешь сделать?",
            reply_markup=get_start_keyboard()
        )

        # Send admin notification
        await send_admin_notification(
            message.bot,
            "waitlist_accepted",
            waitlist_entry["event_id"],
            {
                "user_id": waitlist_entry["user_id"],
                "first_name": waitlist_entry["first_name"],
                "last_name": waitlist_entry["last_name"]
            },
            waitlist_entry["role"]
        )

        # Clear state
        await state.clear()

        logger.info(f"Participant {waitlist_entry['user_id']} completed payment for event {waitlist_entry['event_id']}")

    except Exception as e:
        logger.error(f"Error processing waitlist payment: {e}")
        await message.answer(
            "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()

@router.callback_query(F.data == "payment_confirmed", WaitlistNotificationState.waiting_for_payment)
async def process_waitlist_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Handle payment confirmation for waitlist participants (callback version)."""
    try:
        # Get data from state
        data = await state.get_data()
        waitlist_id = data.get("waitlist_id")
        waitlist_entry = data.get("waitlist_entry")
        event = data.get("event")

        if not waitlist_entry or not waitlist_id or not event:
            await callback.message.edit_text(
                "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
                reply_markup=get_start_keyboard()
            )
            await state.clear()
            await callback.answer()
            return

        # Register the user for the event
        await register_user(
            waitlist_entry["event_id"],
            waitlist_entry["user_id"],
            waitlist_entry["first_name"],
            waitlist_entry["last_name"],
            waitlist_entry["role"],
            REG_STATUS_ACTIVE,
            waitlist_entry["topic"],
            waitlist_entry["description"],
            waitlist_entry["has_presentation"],
            waitlist_entry["comments"]
        )

        # Update waitlist status to accepted
        await update_waitlist_status(waitlist_id, "accepted")

        await state.clear()

        await send_registration_confirmation(
            callback.message.bot,
            callback.from_user.id,
            data.get("event_id"),
            data.get("role")
        )


        # Send admin notification
        await send_admin_notification(
            callback.bot,
            "waitlist_accepted",
            waitlist_entry["event_id"],
            {
                "user_id": waitlist_entry["user_id"],
                "first_name": waitlist_entry["first_name"],
                "last_name": waitlist_entry["last_name"]
            },
            waitlist_entry["role"]
        )

        # Clear state
        await state.clear()

        logger.info(f"Participant {waitlist_entry['user_id']} completed payment for event {waitlist_entry['event_id']}")

    except Exception as e:
        logger.error(f"Error processing waitlist payment: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()

    await callback.answer()

@router.callback_query(F.data.startswith("decline_waitlist_"))
async def process_decline_waitlist(callback: CallbackQuery, state: FSMContext):
    """Handle decline waitlist button click."""
    # Extract waitlist_id from callback data
    waitlist_id = int(callback.data.split("_")[2])

    try:
        # Get waitlist entry
        waitlist_entry = await get_waitlist_entry(waitlist_id)

        if not waitlist_entry:
            await callback.message.edit_text(
                "Ошибка: запись в листе ожидания не найдена.",
                reply_markup=get_start_keyboard()
            )
            await callback.answer()
            return

        # Check if the waitlist entry is still active or notified
        if waitlist_entry["status"] not in ["active", "notified"]:
            await callback.message.edit_text(
                "Это приглашение больше не действительно.",
                reply_markup=get_start_keyboard()
            )
            await callback.answer()
            return

        # Update waitlist status to declined
        await update_waitlist_status(waitlist_id, "declined")

        # Get event details for the confirmation message, passing user_id to filter test events for non-admins
        user_id = callback.from_user.id
        event = await get_event(waitlist_entry["event_id"], user_id)

        # Send confirmation message
        await callback.message.edit_text(
            f"Ты отказался(ась) от участия в мероприятии \"{event['title']}\". Спасибо за ответ!",
            reply_markup=get_start_keyboard()
        )

        # Send admin notification
        await send_admin_notification(
            callback.bot,
            "waitlist_declined",
            waitlist_entry["event_id"],
            {
                "user_id": waitlist_entry["user_id"],
                "first_name": waitlist_entry["first_name"],
                "last_name": waitlist_entry["last_name"]
            },
            waitlist_entry["role"]
        )

        # Check if there's another person on the waitlist
        next_waitlist = await get_next_from_waitlist(waitlist_entry["event_id"], waitlist_entry["role"])

        if next_waitlist:
            # Send notification to the next person on the waitlist
            await send_waitlist_notification(
                callback.bot,
                next_waitlist["user_id"],
                next_waitlist["id"],
                next_waitlist["event_id"],
                next_waitlist["role"]
            )

            logger.info(f"Notified next person {next_waitlist['user_id']} on waitlist for event {next_waitlist['event_id']}")

        logger.info(f"User {waitlist_entry['user_id']} declined waitlist spot for event {waitlist_entry['event_id']}")
    except Exception as e:
        logger.error(f"Error declining waitlist: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отказе от участия. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
            reply_markup=get_start_keyboard()
        )

    await callback.answer()

# Cancel registration handler
@router.callback_query(F.data.startswith("cancel_reg_"))
async def process_cancel_registration(callback: CallbackQuery, state: FSMContext):
    """Handle cancel registration button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        await callback.answer()
        return

    # Check if user is the owner of the registration
    if registration["user_id"] != callback.from_user.id:
        await callback.message.edit_text(
            "У тебя нет прав для отмены этой регистрации.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for confirmation
    await state.update_data(registration_id=registration_id)
    await state.set_state(CancelRegistrationState.waiting_for_confirmation)

    # Get event details, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    event = await get_event(registration["event_id"], user_id)

    # Send confirmation message
    role_text = "спикера" if registration["role"] == ROLE_SPEAKER else "участника"
    await callback.message.edit_text(
        f"Ты уверен(а), что хочешь отменить регистрацию {role_text} на мероприятие \"{event['title']}\"?",
        reply_markup=get_cancel_registration_keyboard(registration_id)
    )

    await callback.answer()

# Confirm cancel registration handler
@router.callback_query(F.data.startswith("confirm_cancel_"))
async def process_confirm_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle confirm cancel registration button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        await callback.answer()
        return

    # Check if user is the owner of the registration
    if registration["user_id"] != callback.from_user.id:
        await callback.message.edit_text(
            "У тебя нет прав для отмены этой регистрации.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    try:
        # Cancel registration
        await cancel_registration(registration_id)

        # Get event details for the notification message, passing user_id to filter test events for non-admins
        user_id = callback.from_user.id
        event = await get_event(registration["event_id"], user_id)

        # Prepare cancellation confirmation message
        role_text = "спикера" if registration["role"] == ROLE_SPEAKER else "участника"
        cancellation_message = (
            f"Твоя регистрация {role_text} на мероприятие {event['title']} — {event['date']} отменена.\n"
            f"Если передумаешь, можешь зарегистрироваться снова, если будут свободные места."
        )

        # Check if there's someone on the waitlist
        next_waitlist = await get_next_from_waitlist(registration["event_id"], registration["role"])

        if next_waitlist:
            # Update waitlist status
            await update_waitlist_status(next_waitlist["id"], REG_STATUS_ACTIVE)

            # Send notification to the next person on the waitlist
            await send_waitlist_notification(
                callback.bot,
                next_waitlist["user_id"],
                next_waitlist["id"],
                registration["event_id"],
                registration["role"]
            )

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
            "Отменено пользователем"
        )

        # Send separate cancellation notification first

        await callback.message.delete()

        from utils.notifications import send_cancellation_confirmation

        # Clear state
        await state.clear()

        await send_cancellation_confirmation(
            callback.bot,
            callback.from_user.id,
            registration["event_id"],
            registration["role"]
        )

        # Log the cancellation
        logger.info(f"Sent cancellation confirmation to user {callback.from_user.id} for event {registration['event_id']}")

    except Exception as e:
        logger.error(f"Error cancelling registration: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при отмене регистрации. Пожалуйста, попробуй позже.",
            reply_markup=get_start_keyboard()
        )

    await callback.answer()

# Edit talk handler
@router.callback_query(F.data.startswith("edit_talk_"))
async def process_edit_talk(callback: CallbackQuery, state: FSMContext):
    """Handle edit talk button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Check if user can edit this talk
    if not await can_edit_talk(callback.from_user.id, registration_id):
        await callback.message.edit_text(
            "У тебя нет прав для редактирования этого доклада.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.edit_text(
            "Регистрация не найдена.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        await callback.answer()
        return

    # Set state to waiting for field
    await state.update_data(registration_id=registration_id)
    await state.set_state(EditTalkState.waiting_for_field)

    # Get event details, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    event = await get_event(registration["event_id"], user_id)

    # Send message with edit options
    await callback.message.edit_text(
        f"Редактирование доклада для мероприятия \"{event['title']}\".\n"
        f"Выбери, что ты хочешь изменить:",
        reply_markup=get_edit_talk_keyboard(registration_id)
    )

    await callback.answer()

# Edit topic handler
@router.callback_query(F.data.startswith("edit_topic_"))
async def process_edit_topic(callback: CallbackQuery, state: FSMContext):
    """Handle edit topic button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Check if user can edit this talk
    if not await can_edit_talk(callback.from_user.id, registration_id):
        await callback.message.edit_text(
            "У тебя нет прав для редактирования этого доклада.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Get registration details
    registration = await get_registration(registration_id)

    # Set state to waiting for topic
    await state.update_data(registration_id=registration_id)
    await state.set_state(EditTalkState.waiting_for_topic)

    # Send message asking for new topic
    await callback.message.edit_text(
        f"Текущая тема: {registration['topic']}\n\n"
        f"Введи новую тему доклада:",
        reply_markup=None
    )

    await callback.answer()

# Edit description handler
@router.callback_query(F.data.startswith("edit_description_"))
async def process_edit_description(callback: CallbackQuery, state: FSMContext):
    """Handle edit description button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Check if user can edit this talk
    if not await can_edit_talk(callback.from_user.id, registration_id):
        await callback.message.edit_text(
            "У тебя нет прав для редактирования этого доклада.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Get registration details
    registration = await get_registration(registration_id)

    # Set state to waiting for description
    await state.update_data(registration_id=registration_id)
    await state.set_state(EditTalkState.waiting_for_description)

    # Send message asking for new description
    await callback.message.edit_text(
        f"Текущее описание: {registration['description']}\n\n"
        f"Введи новое описание доклада:",
        reply_markup=None
    )

    await callback.answer()

# Edit presentation handler
@router.callback_query(F.data.startswith("edit_presentation_"))
async def process_edit_presentation(callback: CallbackQuery, state: FSMContext):
    """Handle edit presentation button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Check if user can edit this talk
    if not await can_edit_talk(callback.from_user.id, registration_id):
        await callback.message.edit_text(
            "У тебя нет прав для редактирования этого доклада.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Get registration details
    registration = await get_registration(registration_id)

    # Set state to waiting for presentation
    await state.update_data(registration_id=registration_id)
    await state.set_state(EditTalkState.waiting_for_presentation)

    # Send message asking for presentation status
    current_status = "Да" if registration["has_presentation"] else "Нет"
    await callback.message.edit_text(
        f"Текущий статус презентации: {current_status}\n\n"
        f"Будет ли у тебя презентация?",
        reply_markup=get_presentation_keyboard()
    )

    await callback.answer()

# Process new topic
@router.message(EditTalkState.waiting_for_topic)
async def process_new_topic(message: Message, state: FSMContext):
    """Process new topic input."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    # Validate topic
    topic = message.text.strip()
    is_valid, error_message = await validate_speaker_data(topic, "placeholder")

    if not is_valid:
        await message.answer(
            f"{error_message}\n\nПожалуйста, введи тему доклада:"
        )
        return

    # Update registration
    await update_registration(registration_id, topic=topic)

    # Send confirmation to user
    await send_talk_update_confirmation(
        message.bot,
        message.from_user.id,
        registration_id,
        "topic"
    )

    # Send notification to admin chat
    registration = await get_registration(registration_id)
    if registration:
        user_info = {
            "first_name": registration["first_name"],
            "last_name": registration["last_name"],
            "topic": topic
        }
        await send_admin_notification(
            message.bot,
            "update",
            registration["event_id"],
            user_info,
            registration["role"],
            "тема доклада"
        )

    # Set state to confirmation
    await state.set_state(EditTalkState.confirmation)

    # Get user's registrations
    registrations = await get_user_registrations(message.from_user.id)

    # Send message with registrations
    await message.answer(
        "Тема доклада успешно обновлена!\n\n"
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

# Process new description
@router.message(EditTalkState.waiting_for_description)
async def process_new_description(message: Message, state: FSMContext):
    """Process new description input."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    # Validate description
    description = message.text.strip()
    is_valid, error_message = await validate_speaker_data("placeholder", description)

    if not is_valid:
        await message.answer(
            f"{error_message}\n\nПожалуйста, введи описание доклада:"
        )
        return

    # Update registration
    await update_registration(registration_id, description=description)

    # Send confirmation to user
    await send_talk_update_confirmation(
        message.bot,
        message.from_user.id,
        registration_id,
        "description"
    )

    # Send notification to admin chat
    registration = await get_registration(registration_id)
    if registration:
        user_info = {
            "first_name": registration["first_name"],
            "last_name": registration["last_name"],
            "topic": registration["topic"] if "topic" in registration else None
        }
        await send_admin_notification(
            message.bot,
            "update",
            registration["event_id"],
            user_info,
            registration["role"],
            "описание доклада"
        )

    # Set state to confirmation
    await state.set_state(EditTalkState.confirmation)

    # Get user's registrations
    registrations = await get_user_registrations(message.from_user.id)

    # Send message with registrations
    await message.answer(
        "Описание доклада успешно обновлено!\n\n"
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

# Process new presentation status (text message)
@router.message(EditTalkState.waiting_for_presentation)
async def process_new_presentation(message: Message, state: FSMContext):
    """Process new presentation status input via text message."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    # Process presentation status
    text = message.text.strip().lower()
    if text not in ["да", "нет"]:
        await message.answer(
            "Пожалуйста, ответь 'Да' или 'Нет':",
            reply_markup=get_presentation_keyboard()
        )
        return

    has_presentation = (text == "да")

    # Update registration
    await update_registration(registration_id, has_presentation=has_presentation)

    # Send confirmation to user
    await send_talk_update_confirmation(
        message.bot,
        message.from_user.id,
        registration_id,
        "has_presentation"
    )

    # Send notification to admin chat
    registration = await get_registration(registration_id)
    if registration:
        user_info = {
            "first_name": registration["first_name"],
            "last_name": registration["last_name"],
            "topic": registration["topic"] if "topic" in registration else None
        }
        await send_admin_notification(
            message.bot,
            "update",
            registration["event_id"],
            user_info,
            registration["role"],
            f"статус презентации: {'Да' if has_presentation else 'Нет'}"
        )

    # Set state to confirmation
    await state.set_state(EditTalkState.confirmation)

    # Get user's registrations
    registrations = await get_user_registrations(message.from_user.id)

    # Send message with registrations
    await message.answer(
        "Статус презентации успешно обновлен!\n\n"
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

# Process new presentation status (callback query)
@router.callback_query(EditTalkState.waiting_for_presentation, F.data.startswith("presentation_"))
async def process_new_presentation_callback(callback: CallbackQuery, state: FSMContext):
    """Process new presentation status input via callback query."""
    # Get data from state
    data = await state.get_data()
    registration_id = data.get("registration_id")

    # Get registration details
    registration = await get_registration(registration_id)

    # Extract response from callback data
    presentation = callback.data.split("_")[1]
    has_presentation = (presentation == "yes")

    # Update registration
    await update_registration(registration_id, has_presentation=has_presentation)

    # Send confirmation to user
    await send_talk_update_confirmation(
        callback.bot,
        callback.from_user.id,
        registration_id,
        "has_presentation"
    )

    # Send notification to admin chat
    registration = await get_registration(registration_id)
    if registration:
        user_info = {
            "first_name": registration["first_name"],
            "last_name": registration["last_name"],
            "topic": registration["topic"] if "topic" in registration else None
        }
        await send_admin_notification(
            callback.bot,
            "update",
            registration["event_id"],
            user_info,
            registration["role"],
            f"статус презентации: {'Да' if has_presentation else 'Нет'}"
        )

    # Set state to confirmation
    await state.set_state(EditTalkState.confirmation)

    # Get user's registrations
    registrations = await get_user_registrations(callback.from_user.id)

    # Send message with registrations
    await callback.message.edit_text(
        "Статус презентации успешно обновлен!\n\n"
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

    # Answer callback query
    await callback.answer()
