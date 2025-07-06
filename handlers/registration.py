import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from utils import log_exception
from utils.validation_helpers import (
    handle_error_and_return
)

from database.db import (
    get_event, 
    count_active_registrations, 
    register_user, 
    add_to_waitlist,
    get_next_from_waitlist,
    update_waitlist_status,
    get_open_events,
    is_on_waitlist
)
from keyboards.keyboards import (
    get_role_keyboard, 
    get_waitlist_keyboard, 
    get_presentation_keyboard,
    get_start_keyboard,
    get_events_keyboard,
    get_payment_confirmation_keyboard
)
from states.states import RegistrationState, WaitlistState, StartState
from utils.validation import (
    is_event_open, 
    has_available_slots, 
    is_already_registered,
    validate_registration_data
)
from utils.notifications import (
    send_registration_confirmation,
    send_waitlist_confirmation,
    send_waitlist_notification,
    send_admin_notification
)
from config import (
    ROLE_SPEAKER, 
    ROLE_PARTICIPANT, 
    REG_STATUS_ACTIVE,
    REVOLUT_DONATION_URL
)
from utils.text_constants import (
    REGISTRATION_EVENT_CLOSED,
    REGISTRATION_ALREADY_REGISTERED,
    REGISTRATION_ROLE_SELECTION,
    REGISTRATION_NO_SLOTS,
    REGISTRATION_ENTER_FIRST_NAME,
    REGISTRATION_EMPTY_FIRST_NAME,
    REGISTRATION_ENTER_LAST_NAME,
    REGISTRATION_EMPTY_LAST_NAME,
    REGISTRATION_ENTER_TOPIC,
    REGISTRATION_EMPTY_TOPIC,
    REGISTRATION_ENTER_DESCRIPTION,
    REGISTRATION_EMPTY_DESCRIPTION,
    REGISTRATION_ENTER_COMMENTS,
    COMMENTS_REQUEST,
    PAYMENT_MESSAGE,
    PAYMENT_CONFIRMATION_ERROR,
    KEYBOARD_PAYMENT_CONFIRMED
)

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize router
router = Router()

# Event selection handler
@router.callback_query(RegistrationState.waiting_for_event, F.data.startswith("event_"))
async def process_event_selection(callback: CallbackQuery, state: FSMContext):
    """Handle event selection."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[1])

    # Check if event is open
    if not await is_event_open(event_id):
        await callback.message.delete()
        await callback.message.answer(
            REGISTRATION_EVENT_CLOSED,
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Check if user is already registered
    user_id = callback.from_user.id
    if await is_already_registered(user_id, event_id):
        await callback.message.delete()
        await callback.message.answer(
            REGISTRATION_ALREADY_REGISTERED,
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return

    # Store event_id in state data
    await state.update_data(event_id=event_id)

    # Get available slots, passing user_id to filter test events for non-admins
    event = await get_event(event_id, user_id)
    speaker_count = await count_active_registrations(event_id, ROLE_SPEAKER)
    participant_count = await count_active_registrations(event_id, ROLE_PARTICIPANT)

    speaker_slots = event["max_speakers"] - speaker_count
    participant_slots = event["max_participants"] - participant_count

    # Set state to waiting for role
    await state.set_state(RegistrationState.waiting_for_role)

    # Send role selection keyboard
    await callback.message.delete()
    await callback.message.answer(
        f"{event['title']}. {REGISTRATION_ROLE_SELECTION}",
        reply_markup=get_role_keyboard(event_id, speaker_slots, participant_slots)
    )

    await callback.answer()

# Role selection handler
@router.callback_query(RegistrationState.waiting_for_role, F.data.startswith("role_"))
async def process_role_selection(callback: CallbackQuery, state: FSMContext):
    """Handle role selection."""
    # Extract event_id and role from callback data
    parts = callback.data.split("_")
    event_id = int(parts[1])
    role = parts[2]

    # Check if there are available slots for this role
    if not await has_available_slots(event_id, role):
        await callback.message.delete()
        await callback.message.answer(
            REGISTRATION_NO_SLOTS,
            reply_markup=get_waitlist_keyboard(event_id, role)
        )
        await state.update_data(role=role)
        await state.set_state(WaitlistState.waiting_for_confirmation)
        await callback.answer()
        return

    # Store role in state data
    await state.update_data(role=role)

    # Set state to waiting for first name
    await state.set_state(RegistrationState.waiting_for_first_name)

    # Ask for first name
    await callback.message.delete()
    await callback.message.answer(REGISTRATION_ENTER_FIRST_NAME)

    await callback.answer()

# First name handler
@router.message(RegistrationState.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    """Handle first name input."""
    first_name = message.text.strip()

    # Validate first name
    if not first_name:
        await message.answer(REGISTRATION_EMPTY_FIRST_NAME)
        return

    # Store first name in state data
    await state.update_data(first_name=first_name)

    # Set state to waiting for last name
    await state.set_state(RegistrationState.waiting_for_last_name)

    # Ask for last name
    await message.answer(REGISTRATION_ENTER_LAST_NAME)

# Last name handler
@router.message(RegistrationState.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    """Handle last name input."""
    last_name = message.text.strip()

    # Validate last name
    if not last_name:
        await message.answer(REGISTRATION_EMPTY_LAST_NAME)
        return

    # Store last name in state data
    await state.update_data(last_name=last_name)

    # Get role from state data
    data = await state.get_data()
    role = data.get("role")

    if role == ROLE_SPEAKER:
        # Set state to waiting for topic
        await state.set_state(RegistrationState.waiting_for_topic)

        # Ask for topic
        await message.answer(REGISTRATION_ENTER_TOPIC)
    else:
        # Set state to waiting for comments
        await state.set_state(RegistrationState.waiting_for_comments)

        # Ask for comments
        await message.answer(COMMENTS_REQUEST)

# Topic handler
@router.message(RegistrationState.waiting_for_topic)
async def process_topic(message: Message, state: FSMContext):
    """Handle topic input."""
    topic = message.text.strip()

    # Validate topic
    if not topic:
        await message.answer(REGISTRATION_EMPTY_TOPIC)
        return

    # Store topic in state data
    await state.update_data(topic=topic)

    # Set state to waiting for description
    await state.set_state(RegistrationState.waiting_for_description)

    # Ask for description
    await message.answer(REGISTRATION_ENTER_DESCRIPTION)

# Description handler
@router.message(RegistrationState.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    """Handle description input."""
    description = message.text.strip()

    # Validate description
    if not description:
        await message.answer(REGISTRATION_EMPTY_DESCRIPTION)
        return

    # Store description in state data
    await state.update_data(description=description)

    # Set state to waiting for presentation
    await state.set_state(RegistrationState.waiting_for_presentation)

    # Ask for presentation
    await message.answer(
        "Будешь показывать слайды?",
        reply_markup=get_presentation_keyboard()
    )

# Presentation handler (text message)
@router.message(RegistrationState.waiting_for_presentation)
async def process_presentation(message: Message, state: FSMContext):
    """Handle presentation input via text message."""
    presentation = message.text.strip().lower()

    # Validate presentation
    if presentation not in ["да", "нет"]:
        await message.answer(
            "Пожалуйста, выбери 'Да' или 'Нет':",
            reply_markup=get_presentation_keyboard()
        )
        return

    # Store presentation in state data
    has_presentation = presentation == "да"
    await state.update_data(has_presentation=has_presentation)

    # Set state to waiting for comments
    await state.set_state(RegistrationState.waiting_for_comments)

    # Ask for comments
    await message.answer(COMMENTS_REQUEST)

# Presentation handler (callback query)
@router.callback_query(RegistrationState.waiting_for_presentation, F.data.startswith("presentation_"))
async def process_presentation_callback(callback: CallbackQuery, state: FSMContext):
    """Handle presentation input via callback query."""
    # Extract response from callback data
    presentation = callback.data.split("_")[1]

    # Store presentation in state data
    has_presentation = presentation == "yes"
    await state.update_data(has_presentation=has_presentation)

    # Set state to waiting for comments
    await state.set_state(RegistrationState.waiting_for_comments)

    # Ask for comments
    await callback.message.delete()
    await callback.message.answer(COMMENTS_REQUEST)

    # Answer callback query
    await callback.answer()

# Payment confirmation handler (text message)
@router.message(RegistrationState.waiting_for_payment)
async def process_payment(message: Message, state: FSMContext):
    """Handle payment confirmation via text message."""
    confirmation = message.text.strip()

    # Validate confirmation
    if confirmation != KEYBOARD_PAYMENT_CONFIRMED:
        await message.answer(
            PAYMENT_CONFIRMATION_ERROR,
            reply_markup=get_payment_confirmation_keyboard()
        )
        return

    # Get all data from state
    data = await state.get_data()

    # Register user
    try:
        await register_user(
            data.get("event_id"),
            message.from_user.id,
            data.get("first_name"),
            data.get("last_name"),
            data.get("role"),
            REG_STATUS_ACTIVE,
            data.get("topic"),
            data.get("description"),
            data.get("has_presentation"),
            data.get("comments"),
            message.from_user.username
        )

        # Send confirmation to user
        await send_registration_confirmation(
            message.bot,
            message.from_user.id,
            data.get("event_id"),
            data.get("role")
        )

        # Send notification to admin chat
        user_info = {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "username": message.from_user.username,
            "topic": data.get("topic")
        }
        await send_admin_notification(
            message.bot,
            "registration",
            data.get("event_id"),
            user_info,
            data.get("role")
        )

        # Clear state
        await state.clear()

        # Send success message
        role_text = "спикер" if data.get("role") == ROLE_SPEAKER else "участник"
        await message.answer(
            f"Что хочешь сделать?",
            reply_markup=get_start_keyboard()
        )

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "state_data": state_data,
                "message_text": message.text
            },
            user_id=message.from_user.id if message.from_user else None,
            event_id=state_data.get("event_id"),
            message="Error registering user"
        )

        await message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуй позже.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()

# Payment confirmation handler (callback query)
@router.callback_query(RegistrationState.waiting_for_payment, F.data == "payment_confirmed")
async def process_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Handle payment confirmation via callback query."""
    # Get all data from state
    data = await state.get_data()

    # Register user
    try:
        await register_user(
            data.get("event_id"),
            callback.from_user.id,
            data.get("first_name"),
            data.get("last_name"),
            data.get("role"),
            REG_STATUS_ACTIVE,
            data.get("topic"),
            data.get("description"),
            data.get("has_presentation"),
            data.get("comments"),
            callback.from_user.username
        )

        # Send confirmation to user
        await send_registration_confirmation(
            callback.bot,
            callback.from_user.id,
            data.get("event_id"),
            data.get("role")
        )

        # Send notification to admin chat
        user_info = {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "username": callback.from_user.username,
            "topic": data.get("topic")
        }
        await send_admin_notification(
            callback.bot,
            "registration",
            data.get("event_id"),
            user_info,
            data.get("role")
        )

        # Clear state
        await state.clear()

        # Send success message
        role_text = "спикер" if data.get("role") == ROLE_SPEAKER else "участник"
        await callback.message.answer(
            f"Что хочешь сделать?",
            reply_markup=get_start_keyboard()
        )

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "state_data": state_data,
                "callback_data": callback.data
            },
            user_id=callback.from_user.id if callback.from_user else None,
            event_id=state_data.get("event_id"),
            message="Error registering user"
        )

        await callback.message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуй позже.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()

    # Answer the callback query to remove the loading indicator
    await callback.answer()

# Comments handler
@router.message(RegistrationState.waiting_for_comments)
async def process_comments(message: Message, state: FSMContext):
    """Handle comments input."""
    comments = message.text.strip()

    # Store comments in state data
    await state.update_data(comments=comments if comments else None)

    # Get all data from state
    data = await state.get_data()

    # Validate all data
    is_valid, error_message = await validate_registration_data(
        data.get("first_name"),
        data.get("last_name"),
        data.get("role"),
        data.get("topic"),
        data.get("description")
    )

    if not is_valid:
        await message.answer(f"Ошибка: {error_message}")
        await state.clear()
        await message.answer(
            "Регистрация отменена. Используй /start, чтобы начать заново.",
            reply_markup=get_start_keyboard()
        )
        return

    # Set state to waiting for payment
    await state.set_state(RegistrationState.waiting_for_payment)

    # Ask for payment
    payment_message = PAYMENT_MESSAGE.format(REVOLUT_DONATION_URL)

    await message.answer(
        payment_message,
        reply_markup=get_payment_confirmation_keyboard(),
        parse_mode="HTML"
    )

# Waitlist confirmation handler
@router.callback_query(WaitlistState.waiting_for_confirmation, F.data.startswith("waitlist_yes_"))
async def process_waitlist_confirmation(callback: CallbackQuery, state: FSMContext):
    """Handle waitlist confirmation."""
    # Extract event_id and role from callback data
    parts = callback.data.split("_")
    event_id = int(parts[2])
    role = parts[3] if len(parts) > 3 else None

    # If role is not provided in callback data or is empty, get it from state
    if not role or role == "":
        data = await state.get_data()
        role = data.get("role")

    # Check if user is already on waitlist
    if await is_on_waitlist(event_id, callback.from_user.id, role):
        return await handle_error_and_return(
            callback,
            "Вы уже в вейт листе.",
            state
        )

    # Store event_id and role in state data
    await state.update_data(event_id=event_id, role=role)

    # Set state to waiting for first name
    await state.set_state(WaitlistState.waiting_for_first_name)

    # Ask for first name
    await callback.message.delete()
    await callback.message.answer("Введи своё имя:")

    await callback.answer()

# Waitlist first name handler
@router.message(WaitlistState.waiting_for_first_name)
async def process_waitlist_first_name(message: Message, state: FSMContext):
    """Handle waitlist first name input."""
    first_name = message.text.strip()

    # Validate first name
    if not first_name:
        await message.answer("Имя не может быть пустым. Пожалуйста, введи своё имя:")
        return

    # Store first name in state data
    await state.update_data(first_name=first_name)

    # Set state to waiting for last name
    await state.set_state(WaitlistState.waiting_for_last_name)

    # Ask for last name
    await message.answer("Введи свою фамилию:")

# Waitlist last name handler
@router.message(WaitlistState.waiting_for_last_name)
async def process_waitlist_last_name(message: Message, state: FSMContext):
    """Handle waitlist last name input."""
    last_name = message.text.strip()

    # Validate last name
    if not last_name:
        await message.answer("Фамилия не может быть пустой. Пожалуйста, введи свою фамилию:")
        return

    # Store last name in state data
    await state.update_data(last_name=last_name)

    # Get role from state data
    data = await state.get_data()
    role = data.get("role")

    if role == ROLE_SPEAKER:
        # Set state to waiting for topic
        await state.set_state(WaitlistState.waiting_for_topic)

        # Ask for topic
        await message.answer("Введи тему доклада:")
    else:
        # Skip payment for waitlist and go directly to comments
        await state.set_state(WaitlistState.waiting_for_comments)

        # Ask for comments
        await message.answer(COMMENTS_REQUEST)

# Waitlist topic handler
@router.message(WaitlistState.waiting_for_topic)
async def process_waitlist_topic(message: Message, state: FSMContext):
    """Handle waitlist topic input."""
    topic = message.text.strip()

    # Validate topic
    if not topic:
        await message.answer("Тема доклада не может быть пустой. Пожалуйста, введи тему доклада:")
        return

    # Store topic in state data
    await state.update_data(topic=topic)

    # Set state to waiting for description
    await state.set_state(WaitlistState.waiting_for_description)

    # Ask for description
    await message.answer("Введи краткое описание доклада:")

# Waitlist description handler
@router.message(WaitlistState.waiting_for_description)
async def process_waitlist_description(message: Message, state: FSMContext):
    """Handle waitlist description input."""
    description = message.text.strip()

    # Validate description
    if not description:
        await message.answer("Описание доклада не может быть пустым. Пожалуйста, введи описание доклада:")
        return

    # Store description in state data
    await state.update_data(description=description)

    # Set state to waiting for presentation
    await state.set_state(WaitlistState.waiting_for_presentation)

    # Ask for presentation
    await message.answer(
        "Будет ли презентация?",
        reply_markup=get_presentation_keyboard()
    )

# Waitlist presentation handler (text message)
@router.message(WaitlistState.waiting_for_presentation)
async def process_waitlist_presentation(message: Message, state: FSMContext):
    """Handle waitlist presentation input via text message."""
    presentation = message.text.strip().lower()

    # Validate presentation
    if presentation not in ["да", "нет"]:
        await message.answer(
            "Пожалуйста, выбери 'Да' или 'Нет':",
            reply_markup=get_presentation_keyboard()
        )
        return

    # Store presentation in state data
    has_presentation = presentation == "да"
    await state.update_data(has_presentation=has_presentation)

    # Skip payment for waitlist and go directly to comments
    await state.set_state(WaitlistState.waiting_for_comments)

    # Ask for comments
    await message.answer(COMMENTS_REQUEST)

# Waitlist presentation handler (callback query)
@router.callback_query(WaitlistState.waiting_for_presentation, F.data.startswith("presentation_"))
async def process_waitlist_presentation_callback(callback: CallbackQuery, state: FSMContext):
    """Handle waitlist presentation input via callback query."""
    # Extract response from callback data
    presentation = callback.data.split("_")[1]

    # Store presentation in state data
    has_presentation = presentation == "yes"
    await state.update_data(has_presentation=has_presentation)

    # Skip payment for waitlist and go directly to comments
    await state.set_state(WaitlistState.waiting_for_comments)

    # Ask for comments
    await callback.message.delete()
    await callback.message.answer(COMMENTS_REQUEST)

    # Answer callback query
    await callback.answer()


# Waitlist comments handler
@router.message(WaitlistState.waiting_for_comments)
async def process_waitlist_comments(message: Message, state: FSMContext):
    """Handle waitlist comments input."""
    comments = message.text.strip()

    # Store comments in state data
    await state.update_data(comments=comments if comments else None)

    # Get all data from state
    data = await state.get_data()

    # Validate all data
    is_valid, error_message = await validate_registration_data(
        data.get("first_name"),
        data.get("last_name"),
        data.get("role"),
        data.get("topic"),
        data.get("description")
    )

    if not is_valid:
        await message.answer(f"Ошибка: {error_message}")
        await state.clear()
        await message.answer(
            "Регистрация в список ожидания отменена. Используй /start, чтобы начать заново.",
            reply_markup=get_start_keyboard()
        )
        return


    # Add to waitlist
    try:
        await add_to_waitlist(
            data.get("event_id"),
            message.from_user.id,
            data.get("first_name"),
            data.get("last_name"),
            data.get("role"),
            REG_STATUS_ACTIVE,
            data.get("topic"),
            data.get("description"),
            data.get("has_presentation"),
            data.get("comments"),
            message.from_user.username
        )

        # Send confirmation to user
        await send_waitlist_confirmation(
            message.bot,
            message.from_user.id,
            data.get("event_id"),
            data.get("role")
        )

        # Send notification to admin chat
        user_info = {
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "username": message.from_user.username,
            "topic": data.get("topic")
        }
        await send_admin_notification(
            message.bot,
            "waitlist",
            data.get("event_id"),
            user_info,
            data.get("role")
        )

        # Clear state
        await state.clear()

    except Exception as e:
        # Get data from state for context
        state_data = await state.get_data()

        # Log the exception with context
        log_exception(
            exception=e,
            context={
                "state_data": state_data,
                "message_text": message.text
            },
            user_id=message.from_user.id if message.from_user else None,
            event_id=state_data.get("event_id"),
            message="Error adding to waitlist"
        )

        await message.answer(
            "Произошла ошибка при добавлении в список ожидания. Пожалуйста, попробуй позже.",
            reply_markup=get_start_keyboard()
        )
        await state.clear()

# Decline waitlist handler
@router.callback_query(WaitlistState.waiting_for_confirmation, F.data == "back_to_start")
async def process_decline_waitlist(callback: CallbackQuery, state: FSMContext):
    """Handle decline waitlist."""
    # Clear state
    await state.clear()

    # Set state to waiting for action
    await state.set_state(StartState.waiting_for_action)

    # Send start message
    await callback.message.delete()
    await callback.message.answer(
        "Привет! Я бот Larnaka Roof Talks 🌇\n\n"
        "Что хочешь сделать?",
        reply_markup=get_start_keyboard()
    )

    await callback.answer()

# Back to events handler
@router.callback_query(F.data == "back_to_events")
async def process_back_to_events(callback: CallbackQuery, state: FSMContext):
    """Handle back to events button click."""
    # Get open events, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    events = await get_open_events(user_id)

    if not events:
        await callback.message.delete()
        await callback.message.answer(
            "Сейчас нет открытых мероприятий. Скоро будут новые!",
            reply_markup=get_start_keyboard()
        )
        await state.clear()
        await state.set_state(StartState.waiting_for_action)
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(RegistrationState.waiting_for_event)

    # Send message with events
    await callback.message.delete()
    await callback.message.answer(
        "Доступные мероприятия:",
        reply_markup=get_events_keyboard(events)
    )

    await callback.answer()
