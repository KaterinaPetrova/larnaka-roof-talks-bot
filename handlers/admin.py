import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import BOT_TOKEN, REVOLUT_DONATION_URL
from utils.notifications import send_admin_notification

from database.db import (
    is_admin,
    get_open_events,
    get_event_statistics,
    get_event_participants,
    get_event_speakers,
    register_user,
    cancel_registration,
    get_registration
)
from keyboards.keyboards import (
    get_admin_keyboard,
    get_admin_events_keyboard,
    get_admin_role_keyboard,
    get_admin_user_list_keyboard,
    get_admin_confirmation_keyboard,
    get_start_keyboard,
    get_payment_confirmation_keyboard
)
from states.states import (
    AdminState,
    StartState,
    AdminAddUserState
)
from text_constants import (
    PAYMENT_MESSAGE,
    PAYMENT_CONFIRMATION_ERROR,
    KEYBOARD_PAYMENT_CONFIRMED
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
        await callback.message.edit_text(
            "Сейчас нет открытых мероприятий.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return

    # Set state to waiting for event
    await state.set_state(AdminState.waiting_for_event)
    await state.update_data(action="stats")

    # Send message with events
    await callback.message.edit_text(
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
        # Check if this is a message confirmation or a remove user confirmation
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
                    logger.error(f"Failed to send message to user {user['user_id']}: {e}")

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

                    # If there's someone on the waitlist, send them a notification
                    if next_waitlist:
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
                logger.error(f"Failed to remove user: {e}")

                # Set state to waiting for admin action
                await state.set_state(AdminState.waiting_for_action)

                # Send error message
                await callback.message.edit_text(
                    f"Не удалось удалить пользователя: {e}",
                    reply_markup=get_admin_keyboard()
                )

    elif current_state == AdminAddUserState.confirmation:
        # This is an add user confirmation
        event_id = data.get("event_id")
        role = data.get("role")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
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
                comments=comments
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
            await callback.message.edit_text(
                f"Слушатель {first_name} {last_name} успешно добавлен.",
                reply_markup=get_admin_keyboard()
            )
        except Exception as e:
            logger.error(f"Failed to add user: {e}")

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

# Back to admin handler
@router.callback_query(F.data == "back_to_admin")
async def process_back_to_admin(callback: CallbackQuery, state: FSMContext):
    """Handle back to admin button click."""
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
        await message.answer("Введи комментарии (или просто отправь '-', если их нет):")

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
    await message.answer("Введи комментарии (или просто отправь '-', если их нет):")

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
    topic = data.get("topic")
    description = data.get("description")
    has_presentation = data.get("has_presentation", False)
    comments = data.get("comments")

    # Set state to confirmation
    await state.set_state(AdminAddUserState.confirmation)

    # Prepare confirmation message
    message_text = (
        f"Ты собираешься добавить нового слушателя:\n\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Роль: {'Спикер' if role == 'speaker' else 'Слушатель'}\n"
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
