import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from utils.logging import log_exception
from utils.validation_helpers import (
    validate_waitlist_entry,
    validate_waitlist_status,
    validate_event,
    validate_registration,
    handle_error_and_return, validate_registration_owner
)

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
    get_start_keyboard,
    get_registration_details_keyboard
)
from states.states import (
    MyEventsState, 
    EditTalkState, 
    CancelRegistrationState,
    StartState,
    WaitlistNotificationState
)
from utils.validation import can_edit_talk, validate_speaker_data, has_available_slots
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
from utils.text_constants import (
    PAYMENT_MESSAGE,
    PAYMENT_CONFIRMATION_ERROR,
    KEYBOARD_PAYMENT_CONFIRMED
)

# Helper functions to reduce code duplication
async def handle_registration_update(bot, user_id, registration_id, field_name, field_value, update_params, notification_detail):
    """
    Handle registration update, send confirmations and notifications.

    Args:
        bot: Bot instance
        user_id: User ID
        registration_id: Registration ID
        field_name: Name of the field being updated (for confirmation)
        field_value: Value to update (not used directly, but passed via update_params)
        update_params: Dictionary of parameters to update in the registration
        notification_detail: Detail for admin notification
    """
    # Update registration
    await update_registration(registration_id, **update_params)

    # Send confirmation to user
    await send_talk_update_confirmation(
        bot,
        user_id,
        registration_id,
        field_name
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
            bot,
            "update",
            registration["event_id"],
            user_info,
            registration["role"],
            notification_detail
        )

async def send_registration_success_message(message_or_callback, state, success_message):
    """
    Set state to confirmation, get user's registrations, and send success message.

    Args:
        message_or_callback: Message or CallbackQuery object
        state: FSMContext
        success_message: Success message to display
    """
    # Set state to confirmation
    await state.set_state(EditTalkState.confirmation)

    # Get user's registrations
    user_id = message_or_callback.from_user.id
    registrations = await get_user_registrations(user_id)

    # Send message with registrations
    if hasattr(message_or_callback, 'answer'):
        # It's a Message object
        await message_or_callback.answer(
            f"{success_message}\n\n"
            "Твои регистрации:",
            reply_markup=get_my_events_keyboard(registrations)
        )
    else:
        # It's a CallbackQuery object
        await message_or_callback.message.edit_text(
            f"{success_message}\n\n"
            "Твои регистрации:",
            reply_markup=get_my_events_keyboard(registrations)
        )

async def validate_talk_edit_permission(callback, registration_id, use_edit_text=False):
    """
    Check if user can edit the talk and handle error message if not.

    Args:
        callback: CallbackQuery object
        registration_id: ID of the registration to check
        use_edit_text: Whether to use edit_text (True) or delete+answer (False)

    Returns:
        bool: True if user can edit the talk, False otherwise
    """
    if not await can_edit_talk(callback.from_user.id, registration_id):
        if use_edit_text:
            await callback.message.edit_text(
                "У тебя нет прав для редактирования этого доклада.",
                reply_markup=get_start_keyboard()
            )
        else:
            await callback.message.delete()
            await callback.message.answer(
                "У тебя нет прав для редактирования этого доклада.",
                reply_markup=get_start_keyboard()
            )
        await callback.answer()
        return False
    return True

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

@router.callback_query(F.data.startswith("view_reg_"))
async def process_view_registration(callback: CallbackQuery, state: FSMContext):
    """Handle view registration button click."""
    # Extract registration_id from callback data
    registration_id = int(callback.data.split("_")[2])

    # Get registration details
    registration = await get_registration(registration_id)

    # Validate registration
    if not await validate_registration(callback, registration):
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        return

    # Check if user is the owner of the registration
    if not await validate_registration_owner(callback, registration, "У тебя нет прав для просмотра этой регистрации."):
        return

    # Set state to waiting for action
    await state.update_data(registration_id=registration_id)
    await state.set_state(MyEventsState.waiting_for_action)

    # Get event details, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    event = await get_event(registration["event_id"], user_id)

    is_speaker = registration["role"] == ROLE_SPEAKER

    # Prepare message
    role_text = "Спикер" if registration["role"] == is_speaker else "Участник"
    message_text = f"📝 Детали регистрации:\n\n"
    message_text += f"🗓 Мероприятие: {event['title']}\n"
    message_text += f"📅 Дата: {event['date']}\n"
    message_text += f"👤 Роль: {role_text}\n"
    message_text += f"👤 Имя: {registration['first_name']} {registration['last_name']}\n"

    if is_speaker and registration["topic"]:
        message_text += f"📢 Тема доклада: {registration['topic']}\n"
        if "description" in registration and registration["description"]:
            message_text += f"📝 Описание: {registration['description']}\n"
        message_text += f"📊 Презентация: {'Да' if registration['has_presentation'] else 'Нет'}\n"

    # Send message with registration details

    await callback.message.delete()
    await callback.message.answer(
        message_text,
        reply_markup=get_registration_details_keyboard(registration_id, is_speaker)
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

        # Validate waitlist entry
        if not await validate_waitlist_entry(callback, waitlist_entry):
            return

        # Check if the waitlist entry is still active or notified
        if not await validate_waitlist_status(callback, waitlist_entry):
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

            logger.warning(f"Speaker {waitlist_entry['user_id']} accepted waitlist spot for event {waitlist_entry['event_id']}")
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
            await callback.message.delete()
            await callback.message.answer(
                payment_message,
                reply_markup=get_payment_confirmation_keyboard(),
                parse_mode="HTML"
            )

            logger.warning(f"Participant {waitlist_entry['user_id']} accepted waitlist spot for event {waitlist_entry['event_id']} - waiting for payment")
    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()
        waitlist_entry = state_data.get("waitlist_entry", {})

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "waitlist_entry": waitlist_entry,
                "callback_data": callback.data,
                "state_data": state_data
            },
            user_id=callback.from_user.id if callback.from_user else None,
            event_id=waitlist_entry.get("event_id"),
            message="Error accepting waitlist"
        )

        await callback.message.delete()
        await callback.message.answer(
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

        logger.warning(f"Participant {waitlist_entry['user_id']} completed payment for event {waitlist_entry['event_id']}")

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()
        waitlist_entry = state_data.get("waitlist_entry", {})

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "waitlist_entry": waitlist_entry,
                "message_text": message.text,
                "state_data": state_data
            },
            user_id=message.from_user.id if message.from_user else None,
            event_id=waitlist_entry.get("event_id"),
            message="Error processing waitlist payment"
        )

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
            return await handle_error_and_return(
                callback,
                "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
                state
            )

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

        logger.warning(f"Participant {waitlist_entry['user_id']} completed payment for event {waitlist_entry['event_id']}")

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()
        waitlist_entry = state_data.get("waitlist_entry", {})

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "waitlist_entry": waitlist_entry,
                "callback_data": callback.data,
                "state_data": state_data
            },
            user_id=callback.from_user.id if callback.from_user else None,
            event_id=waitlist_entry.get("event_id"),
            message="Error processing waitlist payment"
        )

        await handle_error_and_return(
            callback,
            "Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже или свяжитесь с организаторами.",
            state
        )

    await callback.answer()

@router.callback_query(F.data.startswith("decline_waitlist_"))
async def process_decline_waitlist(callback: CallbackQuery, state: FSMContext):
    """Handle decline waitlist button click."""
    # Extract waitlist_id from callback data
    waitlist_id = int(callback.data.split("_")[2])

    try:
        # Get waitlist entry
        waitlist_entry = await get_waitlist_entry(waitlist_id)

        # Validate waitlist entry
        if not await validate_waitlist_entry(callback, waitlist_entry):
            return

        # Check if the waitlist entry is still active or notified
        if not await validate_waitlist_status(callback, waitlist_entry):
            return

        # Update waitlist status to declined
        await update_waitlist_status(waitlist_id, "declined")

        # Get event details for the confirmation message, passing user_id to filter test events for non-admins
        user_id = callback.from_user.id
        event = await get_event(waitlist_entry["event_id"], user_id)

        # Send confirmation message
        await callback.message.delete()
        await callback.message.answer(
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

            logger.warning(f"Notified next person {next_waitlist['user_id']} on waitlist for event {next_waitlist['event_id']}")

        logger.warning(f"User {waitlist_entry['user_id']} declined waitlist spot for event {waitlist_entry['event_id']}")
    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "callback_data": callback.data,
                "state_data": state_data,
                "waitlist_id": waitlist_id
            },
            user_id=callback.from_user.id if callback.from_user else None,
            message="Error declining waitlist"
        )

        await callback.message.delete()
        await callback.message.answer(
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

    # Validate registration
    if not await validate_registration(callback, registration):
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        return

    # Check if user is the owner of the registration
    if not await validate_registration_owner(callback, registration, "У тебя нет прав для отмены этой регистрации."):
        return

    # Set state to waiting for confirmation
    await state.update_data(registration_id=registration_id)
    await state.set_state(CancelRegistrationState.waiting_for_confirmation)

    # Get event details, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    event = await get_event(registration["event_id"], user_id)

    # Send confirmation message
    role_text = "спикера" if registration["role"] == ROLE_SPEAKER else "участника"
    await callback.message.delete()
    await callback.message.answer(
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

    # Validate registration
    if not await validate_registration(callback, registration):
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        return

    # Check if user is the owner of the registration
    if not await validate_registration_owner(callback, registration, "У тебя нет прав для отмены этой регистрации."):
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

        # Check if there are available slots after cancellation
        has_slots = await has_available_slots(registration["event_id"], registration["role"])

        if next_waitlist and has_slots:
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
        logger.warning(f"Sent cancellation confirmation to user {callback.from_user.id} for event {registration['event_id']}")

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "callback_data": callback.data,
                "state_data": state_data,
                "registration_id": registration_id,
                "registration": registration
            },
            user_id=callback.from_user.id if callback.from_user else None,
            event_id=registration.get("event_id") if registration else None,
            message="Error cancelling registration"
        )

        await callback.message.delete()
        await callback.message.answer(
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
    if not await validate_talk_edit_permission(callback, registration_id):
        return

    # Get registration details
    registration = await get_registration(registration_id)

    if not registration:
        await callback.message.delete()
        await callback.message.answer(
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
    await callback.message.delete()
    await callback.message.answer(
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
    if not await validate_talk_edit_permission(callback, registration_id):
        return

    # Get registration details
    registration = await get_registration(registration_id)

    # Set state to waiting for topic
    await state.update_data(registration_id=registration_id)
    await state.set_state(EditTalkState.waiting_for_topic)

    # Send message asking for new topic
    await callback.message.delete()
    await callback.message.answer(
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
    if not await validate_talk_edit_permission(callback, registration_id, use_edit_text=True):
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
    if not await validate_talk_edit_permission(callback, registration_id, use_edit_text=True):
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

    # Handle registration update and notifications
    await handle_registration_update(
        message.bot,
        message.from_user.id,
        registration_id,
        "topic",
        topic,
        {"topic": topic},
        "тема доклада"
    )

    # Send success message
    await send_registration_success_message(
        message,
        state,
        "Тема доклада успешно обновлена!"
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

    # Handle registration update and notifications
    await handle_registration_update(
        message.bot,
        message.from_user.id,
        registration_id,
        "description",
        description,
        {"description": description},
        "описание доклада"
    )

    # Send success message
    await send_registration_success_message(
        message,
        state,
        "Описание доклада успешно обновлено!"
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

    # Handle registration update and notifications
    await handle_registration_update(
        message.bot,
        message.from_user.id,
        registration_id,
        "has_presentation",
        has_presentation,
        {"has_presentation": has_presentation},
        f"статус презентации: {'Да' if has_presentation else 'Нет'}"
    )

    # Send success message
    await send_registration_success_message(
        message,
        state,
        "Статус презентации успешно обновлен!"
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

    # Handle registration update and notifications
    await handle_registration_update(
        callback.bot,
        callback.from_user.id,
        registration_id,
        "has_presentation",
        has_presentation,
        {"has_presentation": has_presentation},
        f"статус презентации: {'Да' if has_presentation else 'Нет'}"
    )

    # Send success message
    await send_registration_success_message(
        callback,
        state,
        "Статус презентации успешно обновлен!"
    )

    # Answer callback query
    await callback.answer()
