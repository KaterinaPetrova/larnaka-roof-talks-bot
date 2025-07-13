import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from utils.validation_helpers import (
    validate_waitlist_entry,
    validate_waitlist_status,
    validate_event,
    validate_registration,
    validate_registration_owner,
    handle_error_and_return
)

from database.db import get_open_events, get_user_registrations, is_admin, count_active_registrations, get_event
from config import ROLE_SPEAKER, ROLE_PARTICIPANT
from keyboards.keyboards import get_start_keyboard, get_events_keyboard, get_my_events_keyboard, get_admin_keyboard, get_waitlist_keyboard
from states.states import StartState, RegistrationState, MyEventsState, AdminState, WaitlistState

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize router
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    user_id = message.from_user.id
    username = message.from_user.username

    chat_id = message.chat.id
    logger.warning(f"User {user_id} (@{username}) started the bot in chat {chat_id}")

    # Clear any previous state
    await state.clear()

    # Set state to waiting for action
    await state.set_state(StartState.waiting_for_action)

    # Send welcome message with start keyboard
    await message.answer(
        "Привет! Я бот Larnaka Roof Talks 🌇\n\n"
        "Что хочешь сделать?",
        reply_markup=get_start_keyboard()
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = (
        "🤖 Larnaka Roof Talks Bot\n\n"
        "Команды:\n"
        "/start - Главное меню\n"
        "/myevents - Посмотреть свои регистрации\n"
        "/admin - Админ-панель (только для админов)\n"
        "/help - Эта подсказка\n"
        "/cancel - Отменить текущее действие\n\n"
        "Если у тебя возникли проблемы, напиши организаторам."
    )

    await message.answer(help_text)

@router.message(Command("myevents"))
async def cmd_my_events(message: Message, state: FSMContext):
    """Handle /myevents command."""
    user_id = message.from_user.id

    # Get user's registrations
    registrations = await get_user_registrations(user_id)

    if not registrations:
        await message.answer(
            "У тебя пока нет регистраций на мероприятия.\n"
            "Используй /start, чтобы зарегистрироваться.",
            reply_markup=get_start_keyboard()
        )
        await state.set_state(StartState.waiting_for_action)
        return

    # Set state to waiting for event
    await state.set_state(MyEventsState.waiting_for_event)

    # Send message with registrations
    await message.answer(
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

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

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command."""
    # Get current state
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нечего отменять. Используй /start, чтобы начать."
        )
        return

    # Clear state
    await state.clear()

    # Send message
    await message.answer(
        "Действие отменено. Используй /start, чтобы начать заново."
    )

@router.callback_query(F.data == "register")
async def process_register(callback: CallbackQuery, state: FSMContext):
    """Handle register button click."""
    # Get open events, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    events = await get_open_events(user_id)

    if not events:
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий. Скоро будут новые!",
            reply_markup=get_start_keyboard()
        )
        return

    # Check which events are full
    full_events = []
    full_speaker_events = []
    full_participant_events = []
    for event in events:
        event_id = event['id']
        speaker_count = await count_active_registrations(event_id, ROLE_SPEAKER)
        participant_count = await count_active_registrations(event_id, ROLE_PARTICIPANT)

        # Check if speaker slots are full
        if speaker_count >= event['max_speakers']:
            full_speaker_events.append(event_id)

        # Check if participant slots are full
        if participant_count >= event['max_participants']:
            full_participant_events.append(event_id)

        # Check if both are full
        if (speaker_count >= event['max_speakers'] and 
            participant_count >= event['max_participants']):
            full_events.append(event_id)

    # Set state to waiting for event
    await state.set_state(RegistrationState.waiting_for_event)

    # Send message with events
    await callback.message.delete()
    await callback.message.answer(
        "Доступные мероприятия:",
        reply_markup=get_events_keyboard(events, full_events, full_speaker_events, full_participant_events)
    )

    # Answer callback query
    await callback.answer()

@router.callback_query(F.data == "my_events")
async def process_my_events(callback: CallbackQuery, state: FSMContext):
    """Handle my events button click."""
    user_id = callback.from_user.id

    # Get user's registrations
    registrations = await get_user_registrations(user_id)

    if not registrations:
        await callback.message.delete()
        await callback.message.answer(
            "У тебя пока нет регистраций на мероприятия.",
            reply_markup=get_start_keyboard()
        )
        return

    # Set state to waiting for event
    await state.set_state(MyEventsState.waiting_for_event)

    # Send message with registrations
    await callback.message.delete()
    await callback.message.answer(
        "Твои регистрации:",
        reply_markup=get_my_events_keyboard(registrations)
    )

    # Answer callback query
    await callback.answer()

@router.callback_query(F.data == "help")
async def process_help(callback: CallbackQuery):
    """Handle help button click."""
    help_text = (
        "🤖 Larnaka Roof Talks Bot\n\n"
        "Команды:\n"
        "/start - Главное меню\n"
        "/myevents - Посмотреть свои регистрации\n"
        "/admin - Админ-панель (только для админов)\n"
        "/help - Эта подсказка\n"
        "/cancel - Отменить текущее действие\n\n"
        "Если у тебя возникли проблемы, напиши организаторам."
    )

    await callback.message.delete()
    await callback.message.answer(
        help_text,
        reply_markup=get_start_keyboard()
    )

    # Answer callback query
    await callback.answer()

@router.callback_query(F.data.startswith("waitlist_event_"))
async def process_waitlist_event(callback: CallbackQuery, state: FSMContext):
    """Handle waitlist event button click."""
    # Extract event_id from callback data
    event_id = int(callback.data.split("_")[2])

    # Get event details, passing user_id to filter test events for non-admins
    user_id = callback.from_user.id
    event = await get_event(event_id, user_id)

    # Validate event
    if not await validate_event(callback, event):
        return

    # Check which roles are full
    speaker_count = await count_active_registrations(event_id, ROLE_SPEAKER)
    participant_count = await count_active_registrations(event_id, ROLE_PARTICIPANT)

    is_speaker_full = speaker_count >= event['max_speakers']
    is_participant_full = participant_count >= event['max_participants']

    # Store event_id in state data
    await state.update_data(event_id=event_id)

    # Determine which role to use for the waitlist
    role = ""
    if is_speaker_full and is_participant_full:
        # Both roles are full, let user choose in the next step
        role = ""
    elif is_speaker_full:
        # Only speaker role is full
        role = ROLE_SPEAKER
    elif is_participant_full:
        # Only participant role is full
        role = ROLE_PARTICIPANT

    # Set state to waiting for confirmation
    await state.set_state(WaitlistState.waiting_for_confirmation)

    # Ask for confirmation
    message_text = f"Места на мероприятие \"{event['title']}\""
    if is_speaker_full and is_participant_full:
        message_text += " заняты для всех ролей 😢"
    elif is_speaker_full:
        message_text += " для спикеров заняты 😢"
    elif is_participant_full:
        message_text += " для участников заняты 😢"

    message_text += "\nХочешь попасть в список ожидания?"

    await callback.message.delete()
    await callback.message.answer(
        message_text,
        reply_markup=get_waitlist_keyboard(event_id, role)
    )

    await callback.answer()

@router.callback_query(F.data == "back_to_start")
async def process_back_to_start(callback: CallbackQuery, state: FSMContext):
    """Handle back to start button click."""
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

    # Answer callback query
    await callback.answer()
