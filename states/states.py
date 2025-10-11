from aiogram.fsm.state import State, StatesGroup

class StartState(StatesGroup):
    """States for the start menu."""
    waiting_for_action = State()

class RegistrationState(StatesGroup):
    """States for the registration process."""
    waiting_for_event = State()
    waiting_for_role = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_topic = State()
    waiting_for_description = State()
    waiting_for_presentation = State()
    waiting_for_payment = State()
    waiting_for_comments = State()
    confirmation = State()

class WaitlistState(StatesGroup):
    """States for the waitlist process."""
    waiting_for_confirmation = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_topic = State()
    waiting_for_description = State()
    waiting_for_presentation = State()
    waiting_for_comments = State()
    confirmation = State()

class MyEventsState(StatesGroup):
    """States for managing user's events."""
    waiting_for_event = State()
    waiting_for_action = State()

class EditTalkState(StatesGroup):
    """States for editing a talk."""
    waiting_for_field = State()
    waiting_for_topic = State()
    waiting_for_description = State()
    waiting_for_presentation = State()
    confirmation = State()

class CancelRegistrationState(StatesGroup):
    """States for cancelling a registration."""
    waiting_for_confirmation = State()

class AdminState(StatesGroup):
    """States for admin actions."""
    waiting_for_action = State()
    waiting_for_event = State()
    waiting_for_role = State()
    waiting_for_user = State()
    waiting_for_message = State()
    waiting_for_slot_type = State()
    waiting_for_slot_count = State()
    confirmation = State()

class AdminAddUserState(StatesGroup):
    """States for admin adding a user."""
    waiting_for_event = State()
    waiting_for_role = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_username = State()
    waiting_for_topic = State()
    waiting_for_description = State()
    waiting_for_presentation = State()
    waiting_for_payment = State()
    waiting_for_comments = State()
    confirmation = State()

class WaitlistNotificationState(StatesGroup):
    """States for waitlist notification process."""
    waiting_for_response = State()
    waiting_for_payment = State()

class AdminAddAdminState(StatesGroup):
    """States for admin adding another admin."""
    waiting_for_user_id = State()
    confirmation = State()

class AdminEditTalkState(StatesGroup):
    """States for admin editing a talk."""
    waiting_for_event = State()
    waiting_for_speaker = State()
    waiting_for_field = State()
    waiting_for_topic = State()
    waiting_for_description = State()
    waiting_for_presentation = State()
    confirmation = State()

class AdminCreateEventState(StatesGroup):
    """States for admin creating a new event."""
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_description = State()
    waiting_for_max_speakers = State()
    waiting_for_max_participants = State()
    waiting_for_status = State()
    waiting_for_is_test = State()
    confirmation = State()

class AdminEditEventState(StatesGroup):
    """States for admin editing an event."""
    waiting_for_event = State()
    waiting_for_field = State()
    waiting_for_value = State()
    confirmation = State()
