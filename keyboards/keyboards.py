from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import ROLE_SPEAKER, ROLE_PARTICIPANT
from utils.text_constants import (
    KEYBOARD_REGISTER,
    KEYBOARD_MY_EVENTS,
    KEYBOARD_HELP,
    KEYBOARD_BACK,
    KEYBOARD_SPEAKER,
    KEYBOARD_PARTICIPANT,
    KEYBOARD_SPEAKER_SLOTS,
    KEYBOARD_SPEAKER_WAITLIST,
    KEYBOARD_PARTICIPANT_SLOTS,
    KEYBOARD_PARTICIPANT_WAITLIST,
    KEYBOARD_YES_WAITLIST,
    KEYBOARD_NO,
    KEYBOARD_YES,
    KEYBOARD_PAYMENT_CONFIRMED,
    KEYBOARD_SPEAKER_LABEL,
    KEYBOARD_PARTICIPANT_LABEL,
    EVENT_FORMAT,
    REGISTRATION_FORMAT
)

# Start menu keyboard
def get_start_keyboard():
    """Get the start menu keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=KEYBOARD_REGISTER, callback_data="register")],
        [InlineKeyboardButton(text=KEYBOARD_MY_EVENTS, callback_data="my_events")],
        [InlineKeyboardButton(text=KEYBOARD_HELP, callback_data="help")]
    ])
    return keyboard

# Event selection keyboard
def get_events_keyboard(events, full_events=None, full_speaker_events=None, full_participant_events=None):
    """Get keyboard with available events."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for event in events:
        event_id = event['id']

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=EVENT_FORMAT.format(event['title'], event['date']),
                callback_data=f"event_{event_id}"
            )
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text=KEYBOARD_BACK, callback_data="back_to_start")
    ])

    return keyboard

# Role selection keyboard
def get_role_keyboard(event_id, speaker_slots, participant_slots, speaker_has_waitlist=False, participant_has_waitlist=False):
    """Get keyboard for role selection."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=KEYBOARD_SPEAKER + (KEYBOARD_SPEAKER_WAITLIST if speaker_has_waitlist or speaker_slots <= 0 else KEYBOARD_SPEAKER_SLOTS.format(speaker_slots)), 
            callback_data=f"role_{event_id}_{ROLE_SPEAKER}"
        )],
        [InlineKeyboardButton(
            text=KEYBOARD_PARTICIPANT + (KEYBOARD_PARTICIPANT_WAITLIST if participant_has_waitlist or participant_slots <= 0 else KEYBOARD_PARTICIPANT_SLOTS.format(participant_slots)),
            callback_data=f"role_{event_id}_{ROLE_PARTICIPANT}"
        )],
        [InlineKeyboardButton(text=KEYBOARD_BACK, callback_data="back_to_events")]
    ])
    return keyboard

# Waitlist confirmation keyboard
def get_waitlist_keyboard(event_id, role):
    """Get keyboard for waitlist confirmation."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=KEYBOARD_YES_WAITLIST, callback_data=f"waitlist_yes_{event_id}_{role}"),
            InlineKeyboardButton(text=KEYBOARD_NO, callback_data="back_to_start")
        ]
    ])
    return keyboard

# Yes/No keyboard
def get_yes_no_keyboard(yes_callback, no_callback):
    """Get a simple Yes/No keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=KEYBOARD_YES, callback_data=yes_callback),
            InlineKeyboardButton(text=KEYBOARD_NO, callback_data=no_callback)
        ]
    ])
    return keyboard

# Presentation keyboard
def get_presentation_keyboard():
    """Get keyboard for presentation question."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=KEYBOARD_YES, callback_data="presentation_yes"),
            InlineKeyboardButton(text=KEYBOARD_NO, callback_data="presentation_no")
        ]
    ])
    return keyboard

# Payment confirmation keyboard
def get_payment_confirmation_keyboard():
    """Return keyboard with payment confirmation button."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=KEYBOARD_PAYMENT_CONFIRMED, callback_data="payment_confirmed")]
    ])
    return keyboard

# My events keyboard
def get_my_events_keyboard(registrations):
    """Get keyboard with user's registrations."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for reg in registrations:
        role_emoji = "🎤" if reg["role"] == ROLE_SPEAKER else "🙋‍♀️"
        role_text = KEYBOARD_SPEAKER_LABEL if reg["role"] == ROLE_SPEAKER else KEYBOARD_PARTICIPANT_LABEL

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=REGISTRATION_FORMAT.format(role_emoji, reg['date'], reg['title'], role_text),
                callback_data=f"view_reg_{reg['id']}"
            )
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")
    ])

    return keyboard

# Edit talk keyboard
def get_edit_talk_keyboard(registration_id):
    """Get keyboard for editing a talk."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. Тему", callback_data=f"edit_topic_{registration_id}")],
        [InlineKeyboardButton(text="2. Описание", callback_data=f"edit_description_{registration_id}")],
        [InlineKeyboardButton(text="3. Презентацию (да/нет)", callback_data=f"edit_presentation_{registration_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_my_events")]
    ])
    return keyboard

# Cancel registration keyboard
def get_registration_details_keyboard(registration_id, is_speaker=False):
    """Get keyboard for registration details."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if is_speaker:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="Изменить доклад", callback_data=f"edit_talk_{registration_id}")
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="Отменить участие", callback_data=f"cancel_reg_{registration_id}")
    ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_my_events")
    ])

    return keyboard

def get_cancel_registration_keyboard(registration_id):
    """Get keyboard for cancelling a registration."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, отменить", callback_data=f"confirm_cancel_{registration_id}"),
            InlineKeyboardButton(text="Нет", callback_data="back_to_my_events")
        ]
    ])
    return keyboard

# Waitlist notification keyboard
def get_waitlist_notification_keyboard(waitlist_id):
    """Get keyboard for waitlist notification."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, беру место", callback_data=f"accept_waitlist_{waitlist_id}"),
            InlineKeyboardButton(text="Нет, спасибо", callback_data=f"decline_waitlist_{waitlist_id}")
        ]
    ])
    return keyboard

# Admin menu keyboard
def get_admin_keyboard():
    """Get the admin menu keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Создать мероприятие", callback_data="admin_create_event")],
        [InlineKeyboardButton(text="🛠️ Редактировать мероприятие", callback_data="admin_edit_event")],
        [InlineKeyboardButton(text="📋 Посмотреть слушателей", callback_data="admin_view_participants")],
        [InlineKeyboardButton(text="👤 Посмотреть спикеров", callback_data="admin_view_speakers")],
        [InlineKeyboardButton(text="📢 Написать всем", callback_data="admin_message_all")],
        [InlineKeyboardButton(text="➕ Добавить спикера вручную", callback_data="admin_add_speaker")],
        [InlineKeyboardButton(text="➕ Добавить слушателя вручную", callback_data="admin_add_user")],
        [InlineKeyboardButton(text="🗑️ Удалить слушателя", callback_data="admin_remove_user")],
        [InlineKeyboardButton(text="✏️ Редактировать доклад", callback_data="admin_edit_talk")],
        [InlineKeyboardButton(text="🔄 Изменить количество мест", callback_data="admin_change_slots")],
        [InlineKeyboardButton(text="📈 Посмотреть статистику", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📋 Вейт-лист", callback_data="admin_view_waitlist")],
        [InlineKeyboardButton(text="⏱️ Обработать вейт-лист", callback_data="admin_process_waitlist")],
        [InlineKeyboardButton(text="💾 Выгрузить базу данных", callback_data="admin_export_db")],
        [InlineKeyboardButton(text="👑 Добавить администратора", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")]
    ])
    return keyboard

# Admin confirmation keyboard
def get_admin_confirmation_keyboard():
    """Get the admin confirmation keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="back_to_admin")
        ]
    ])
    return keyboard

# Admin event selection keyboard
def get_admin_events_keyboard(events):
    """Get keyboard with events for admin."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📆 {event['title']} — {event['date']}", callback_data=f"admin_event_{event['id']}")] 
        for event in events
    ] + [[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]])
    return keyboard

# Admin role selection keyboard
def get_admin_role_keyboard(event_id):
    """Get keyboard for role selection in admin mode."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Спикеры", callback_data=f"admin_role_{event_id}_{ROLE_SPEAKER}")],
        [InlineKeyboardButton(text="🙋‍♀️ Слушатели", callback_data=f"admin_role_{event_id}_{ROLE_PARTICIPANT}")],
        [InlineKeyboardButton(text="👥 Все", callback_data=f"admin_role_{event_id}_all")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_events")]
    ])
    return keyboard

# Admin user list keyboard
def get_admin_user_list_keyboard(users, event_id, role, action="view"):
    """Get keyboard with user list for admin."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for user in users:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{user['first_name']} {user['last_name']}",
                callback_data=f"admin_user_{action}_{user['id']}"
            )
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_admin_role_{event_id}")
    ])

    return keyboard

# Admin slot type selection keyboard
def get_admin_slot_type_keyboard(event_id):
    """Get keyboard for selecting slot type to change."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Спикеры", callback_data=f"admin_slot_type_{event_id}_speaker")],
        [InlineKeyboardButton(text="🙋‍♀️ Слушатели", callback_data=f"admin_slot_type_{event_id}_participant")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_events")]
    ])
    return keyboard

def get_admin_speaker_list_keyboard(speakers, event_id):
    """Get keyboard with speaker list for admin to edit talks."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for speaker in speakers:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{speaker['first_name']} {speaker['last_name']} - {speaker['topic']}",
                callback_data=f"admin_edit_speaker_{speaker['id']}"
            )
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_admin_events")
    ])

    return keyboard

def get_admin_edit_talk_keyboard(registration_id):
    """Get keyboard for admin editing a talk."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. Тему", callback_data=f"admin_edit_topic_{registration_id}")],
        [InlineKeyboardButton(text="2. Описание", callback_data=f"admin_edit_description_{registration_id}")],
        [InlineKeyboardButton(text="3. Презентацию (да/нет)", callback_data=f"admin_edit_presentation_{registration_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_speakers")]
    ])
    return keyboard

# Admin event edit keyboard

def get_admin_event_edit_keyboard(event_id: int):
    """Get keyboard for editing event fields."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data=f"admin_edit_event_field_{event_id}_title")],
        [InlineKeyboardButton(text="📅 Дата", callback_data=f"admin_edit_event_field_{event_id}_date")],
        [InlineKeyboardButton(text="🧾 Описание", callback_data=f"admin_edit_event_field_{event_id}_description")],
        [InlineKeyboardButton(text="🎤 Места спикеров", callback_data=f"admin_edit_event_field_{event_id}_max_speakers")],
        [InlineKeyboardButton(text="🙋‍♀️ Места слушателей", callback_data=f"admin_edit_event_field_{event_id}_max_participants")],
        [InlineKeyboardButton(text="🚦 Статус", callback_data=f"admin_edit_event_field_{event_id}_status")],
        [InlineKeyboardButton(text="🧪 Тестовое", callback_data=f"admin_edit_event_field_{event_id}_is_test")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_events")]
    ])
    return keyboard


def get_admin_event_status_keyboard(event_id: int):
    """Keyboard to pick event status."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыто", callback_data=f"admin_edit_event_status_{event_id}_open")],
        [InlineKeyboardButton(text="Закрыто", callback_data=f"admin_edit_event_status_{event_id}_closed")],
        [InlineKeyboardButton(text="Завершено", callback_data=f"admin_edit_event_status_{event_id}_completed")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_edit_event_field_{event_id}_back")]
    ])
    return keyboard


def get_yes_no_keyboard(yes_callback: str, no_callback: str):
    """Reusable yes/no keyboard (duplicated signature for type hints)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=yes_callback),
            InlineKeyboardButton(text="Нет", callback_data=no_callback),
        ]
    ])
