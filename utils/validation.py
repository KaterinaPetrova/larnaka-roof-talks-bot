import logging
from database.db import (
    get_event, 
    count_active_registrations, 
    get_user_registrations
)
from config import ROLE_SPEAKER, ROLE_PARTICIPANT

# Initialize logger
logger = logging.getLogger(__name__)

async def is_event_open(event_id):
    """Check if an event is open for registration."""
    event = await get_event(event_id)
    if not event:
        logger.warning(f"Event {event_id} not found")
        return False
    
    return event["status"] == "open"

async def has_available_slots(event_id, role):
    """Check if there are available slots for a specific role."""
    event = await get_event(event_id)
    if not event:
        logger.warning(f"Event {event_id} not found")
        return False
    
    current_count = await count_active_registrations(event_id, role)
    
    if role == ROLE_SPEAKER:
        return current_count < event["max_speakers"]
    elif role == ROLE_PARTICIPANT:
        return current_count < event["max_participants"]
    else:
        logger.warning(f"Invalid role: {role}")
        return False

async def is_already_registered(user_id, event_id):
    """Check if a user is already registered for an event."""
    registrations = await get_user_registrations(user_id)
    
    for reg in registrations:
        if reg["event_id"] == event_id:
            logger.info(f"User {user_id} is already registered for event {event_id}")
            return True
    
    return False

async def validate_speaker_data(topic, description):
    """Validate speaker data."""
    if not topic or not topic.strip():
        return False, "Тема доклада не может быть пустой"
    
    if not description or not description.strip():
        return False, "Описание доклада не может быть пустым"
    
    return True, ""

async def validate_registration_data(first_name, last_name, role, topic=None, description=None):
    """Validate registration data."""
    if not first_name or not first_name.strip():
        return False, "Имя не может быть пустым"
    
    if not last_name or not last_name.strip():
        return False, "Фамилия не может быть пустой"
    
    if role not in [ROLE_SPEAKER, ROLE_PARTICIPANT]:
        return False, f"Некорректная роль: {role}"
    
    if role == ROLE_SPEAKER:
        return await validate_speaker_data(topic, description)
    
    return True, ""

async def can_edit_talk(user_id, registration_id):
    """Check if a user can edit a talk."""
    registrations = await get_user_registrations(user_id)
    
    for reg in registrations:
        if reg["id"] == registration_id and reg["role"] == ROLE_SPEAKER:
            return True
    
    return False