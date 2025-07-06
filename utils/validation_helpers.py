"""
Helper functions for validating entities and handling common error cases.
"""
import logging
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from keyboards.keyboards import get_start_keyboard

logger = logging.getLogger(__name__)

async def validate_waitlist_entry(callback: CallbackQuery, waitlist_entry, error_message=None):
    """
    Validate if a waitlist entry exists.

    Args:
        callback: The callback query
        waitlist_entry: The waitlist entry to validate
        error_message: Custom error message (optional)

    Returns:
        bool: True if the waitlist entry exists, False otherwise
    """
    if not waitlist_entry:
        await callback.message.delete()
        await callback.message.answer(
            error_message or "Ошибка: запись в листе ожидания не найдена.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return False
    return True

async def validate_waitlist_status(callback: CallbackQuery, waitlist_entry, valid_statuses=None, error_message=None):
    """
    Validate if a waitlist entry has a valid status.

    Args:
        callback: The callback query
        waitlist_entry: The waitlist entry to validate
        valid_statuses: List of valid statuses (default: ["active", "notified"])
        error_message: Custom error message (optional)

    Returns:
        bool: True if the waitlist entry has a valid status, False otherwise
    """
    if valid_statuses is None:
        valid_statuses = ["active", "notified"]

    if waitlist_entry["status"] not in valid_statuses:
        await callback.message.delete()
        await callback.message.answer(
            error_message or "Это приглашение больше не действительно.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return False
    return True

async def validate_event(callback: CallbackQuery, event, error_message=None):
    """
    Validate if an event exists.

    Args:
        callback: The callback query
        event: The event to validate
        error_message: Custom error message (optional)

    Returns:
        bool: True if the event exists, False otherwise
    """
    if not event:
        await callback.message.delete()
        await callback.message.answer(
            error_message or "Мероприятие не найдено.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return False
    return True

async def validate_registration(callback: CallbackQuery, registration, error_message=None):
    """
    Validate if a registration exists.

    Args:
        callback: The callback query
        registration: The registration to validate
        error_message: Custom error message (optional)

    Returns:
        bool: True if the registration exists, False otherwise
    """
    if not registration:
        await callback.message.delete()
        await callback.message.answer(
            error_message or "Регистрация не найдена.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return False
    return True

async def validate_registration_owner(callback: CallbackQuery, registration, error_message=None):
    """
    Validate if the user is the owner of the registration.

    Args:
        callback: The callback query
        registration: The registration to validate
        error_message: Custom error message (optional)

    Returns:
        bool: True if the user is the owner of the registration, False otherwise
    """
    if registration["user_id"] != callback.from_user.id:
        await callback.message.delete()
        await callback.message.answer(
            error_message or "У тебя нет прав для изменения этой регистрации.",
            reply_markup=get_start_keyboard()
        )
        await callback.answer()
        return False
    return True

async def handle_error_and_return(callback_or_message, error_message, state=None):
    """
    Handle an error by showing a message and optionally clearing the state.

    Args:
        callback_or_message: The callback query or message
        error_message: The error message to show
        state: The FSM context (optional)

    Returns:
        bool: Always returns False
    """
    is_callback = isinstance(callback_or_message, CallbackQuery)

    if is_callback:
        await callback_or_message.message.delete()
        await callback_or_message.message.answer(
            error_message,
            reply_markup=get_start_keyboard()
        )
        await callback_or_message.answer()
    else:
        await callback_or_message.answer(
            error_message,
            reply_markup=get_start_keyboard()
        )

    if state:
        await state.clear()

    return False
