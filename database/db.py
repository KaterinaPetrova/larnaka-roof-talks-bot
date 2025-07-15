import aiosqlite
import logging
from datetime import datetime
from config import DB_NAME

# Initialize logger
logger = logging.getLogger(__name__)

async def init_db():
    """Initialize the database with required tables if they don't exist."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Create events table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            max_speakers INTEGER NOT NULL,
            max_participants INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_test BOOLEAN DEFAULT 0
        )
        ''')

        # Create registrations table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            username TEXT,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            topic TEXT,
            description TEXT,
            has_presentation BOOLEAN,
            comments TEXT,
            registered_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE (event_id, user_id, role)
        )
        ''')

        # Create waitlist table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            username TEXT,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            topic TEXT,
            description TEXT,
            has_presentation BOOLEAN,
            comments TEXT,
            added_at TEXT NOT NULL,
            notified_at TEXT,
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE (event_id, user_id, role)
        )
        ''')

        # Create admins table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            added_at TEXT NOT NULL
        )
        ''')

        await db.commit()
        logger.info("Database initialized successfully")

async def migrate_db():
    """Migrate the database schema for existing databases."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Check if is_test column exists in events table
        cursor = await db.execute("PRAGMA table_info(events)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Add is_test column if it doesn't exist
        if 'is_test' not in column_names:
            await db.execute("ALTER TABLE events ADD COLUMN is_test BOOLEAN DEFAULT 0")
            await db.commit()
            logger.info("Added is_test column to events table")
        else:
            logger.info("is_test column already exists in events table")

        # Check if username column exists in registrations table
        cursor = await db.execute("PRAGMA table_info(registrations)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Add username column if it doesn't exist
        if 'username' not in column_names:
            await db.execute("ALTER TABLE registrations ADD COLUMN username TEXT")
            await db.commit()
            logger.info("Added username column to registrations table")
        else:
            logger.info("username column already exists in registrations table")

        # Check if username column exists in waitlist table
        cursor = await db.execute("PRAGMA table_info(waitlist)")
        columns = await cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Add username column if it doesn't exist
        if 'username' not in column_names:
            await db.execute("ALTER TABLE waitlist ADD COLUMN username TEXT")
            await db.commit()
            logger.info("Added username column to waitlist table")
        else:
            logger.info("username column already exists in waitlist table")

# Event operations
async def create_event(title, date, description, max_speakers, max_participants, status, is_test=False):
    """Create a new event."""
    async with aiosqlite.connect(DB_NAME) as db:
        created_at = datetime.now().isoformat()
        await db.execute(
            '''INSERT INTO events (title, date, description, max_speakers, max_participants, status, created_at, is_test) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (title, date, description, max_speakers, max_participants, status, created_at, is_test)
        )
        await db.commit()
        return await db.execute_fetchall("SELECT last_insert_rowid()")

async def get_open_events(user_id=None):
    """
    Get all open events.
    If user_id is provided, filters test events for non-admin users.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        # Check if user is admin
        is_user_admin = False
        if user_id:
            is_user_admin = await is_admin(user_id)

        # If user is admin or no user_id provided, show all events
        if is_user_admin or user_id is None:
            cursor = await db.execute("SELECT * FROM events WHERE status = 'open' ORDER BY date")
        else:
            # For non-admin users, filter out test events
            cursor = await db.execute("SELECT * FROM events WHERE status = 'open' AND (is_test = 0 OR is_test IS NULL) ORDER BY date")

        return await cursor.fetchall()

async def get_event(event_id, user_id=None):
    """
    Get event by ID.
    If user_id is provided, checks if user is admin before returning test events.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        # Get the event
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        event = await cursor.fetchone()

        # If event not found, return None
        if not event:
            return None

        # If event is not a test event, return it
        if not event['is_test']:
            return event

        # If event is a test event, check if user is admin
        if user_id:
            is_user_admin = await is_admin(user_id)
            if is_user_admin:
                return event
            else:
                # Non-admin users cannot access test events
                return None
        else:
            # If no user_id provided, return the event (admin context assumed)
            return event

async def update_event_status(event_id, status):
    """Update event status."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
        await db.commit()

async def update_event_slots(event_id, max_speakers=None, max_participants=None):
    """Update the number of slots for an event."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Get current values if not provided
        if max_speakers is None or max_participants is None:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT max_speakers, max_participants FROM events WHERE id = ?", (event_id,))
            event = await cursor.fetchone()

            if not event:
                logger.error(f"Event {event_id} not found")
                return False

            max_speakers = max_speakers if max_speakers is not None else event["max_speakers"]
            max_participants = max_participants if max_participants is not None else event["max_participants"]

        # Update the event
        await db.execute(
            "UPDATE events SET max_speakers = ?, max_participants = ? WHERE id = ?", 
            (max_speakers, max_participants, event_id)
        )
        await db.commit()
        logger.info(f"Updated slots for event {event_id}: speakers={max_speakers}, participants={max_participants}")
        return True

# Registration operations
async def register_user(event_id, user_id, first_name, last_name, role, status, topic=None, description=None, has_presentation=None, comments=None, username=None):
    """Register a user for an event."""
    async with aiosqlite.connect(DB_NAME) as db:
        registered_at = datetime.now().isoformat()

        # Check if user already has a registration for this event and role
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id FROM registrations WHERE event_id = ? AND user_id = ? AND role = ?",
            (event_id, user_id, role)
        )
        existing_registration = await cursor.fetchone()

        if existing_registration:
            # Update existing registration
            await db.execute(
                '''UPDATE registrations SET 
                   first_name = ?, last_name = ?, username = ?, status = ?, 
                   topic = ?, description = ?, has_presentation = ?, 
                   comments = ?, registered_at = ? 
                   WHERE id = ?''',
                (first_name, last_name, username, status, topic, description, 
                 has_presentation, comments, registered_at, existing_registration["id"])
            )
            logger.info(f"Updated existing registration for user {user_id} in event {event_id} with role {role}")
        else:
            # Insert new registration
            await db.execute(
                '''INSERT INTO registrations 
                   (event_id, user_id, first_name, last_name, username, role, status, topic, description, has_presentation, comments, registered_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (event_id, user_id, first_name, last_name, username, role, status, topic, description, has_presentation, comments, registered_at)
            )
            logger.info(f"Created new registration for user {user_id} in event {event_id} with role {role}")

        await db.commit()

async def get_user_registrations(user_id):
    """Get all registrations for a user."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            '''SELECT r.*, e.title, e.date FROM registrations r 
               JOIN events e ON r.event_id = e.id 
               WHERE r.user_id = ? AND r.status = 'active' 
               ORDER BY e.date''',
            (user_id,)
        )
        return await cursor.fetchall()

async def get_registration(registration_id):
    """Get registration by ID."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,))
        return await cursor.fetchone()

async def update_registration(registration_id, **kwargs):
    """Update registration details."""
    async with aiosqlite.connect(DB_NAME) as db:
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(registration_id)

        await db.execute(f"UPDATE registrations SET {set_clause} WHERE id = ?", values)
        await db.commit()

async def cancel_registration(registration_id):
    """Cancel a registration."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE registrations SET status = 'cancelled' WHERE id = ?", (registration_id,))
        await db.commit()

async def count_active_registrations(event_id, role):
    """Count active registrations for an event by role."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND role = ? AND status = 'active'",
            (event_id, role)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

# Waitlist operations
async def add_to_waitlist(event_id, user_id, first_name, last_name, role, status, topic=None, description=None, has_presentation=None, comments=None, username=None):
    """Add a user to the waitlist."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        added_at = datetime.now().isoformat()

        # Check if user already has an entry in the waitlist for this event and role
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, status FROM waitlist WHERE event_id = ? AND user_id = ? AND role = ?",
            (event_id, user_id, role)
        )
        existing_entry = await cursor.fetchone()

        if existing_entry:
            # User already has an entry, update it instead of inserting a new one
            await db.execute(
                '''UPDATE waitlist 
                   SET status = ?, first_name = ?, last_name = ?, username = ?, 
                       topic = ?, description = ?, has_presentation = ?, comments = ?, added_at = ? 
                   WHERE id = ?''',
                (status, first_name, last_name, username, topic, description, has_presentation, comments, added_at, existing_entry['id'])
            )
            await db.commit()
            logger.warning(f"Updated user {user_id} in waitlist for event {event_id} with role {role} from status '{existing_entry['status']}' to '{status}'")
        else:
            # No existing entry, insert a new one
            await db.execute(
                '''INSERT INTO waitlist 
                   (event_id, user_id, first_name, last_name, username, role, status, topic, description, has_presentation, comments, added_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (event_id, user_id, first_name, last_name, username, role, status, topic, description, has_presentation, comments, added_at)
            )
            await db.commit()
            logger.warning(f"Added user {user_id} to waitlist for event {event_id} with role {role} and status {status}")

async def get_next_from_waitlist(event_id, role):
    """Get the next person from the waitlist for a specific event and role."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM waitlist WHERE event_id = ? AND role = ? AND status = 'active' ORDER BY added_at LIMIT 1",
            (event_id, role)
        )
        result = await cursor.fetchone()
        if result:
            logger.warning(f"Found next person on waitlist for event {event_id} with role {role}: user {result['user_id']}")
        else:
            logger.warning(f"No one found on waitlist for event {event_id} with role {role}")
        return result

async def update_waitlist_status(waitlist_id, status, notified_at=None):
    """Update waitlist status."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        # Get the waitlist entry first to include user_id and event_id in the log
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT user_id, event_id FROM waitlist WHERE id = ?", (waitlist_id,))
        entry = await cursor.fetchone()

        if notified_at:
            await db.execute(
                "UPDATE waitlist SET status = ?, notified_at = ? WHERE id = ?",
                (status, notified_at, waitlist_id)
            )
            if entry:
                logger.warning(f"Updated waitlist entry {waitlist_id} for user {entry['user_id']} and event {entry['event_id']} to status '{status}' with notified_at {notified_at}")
            else:
                logger.warning(f"Updated waitlist entry {waitlist_id} to status '{status}' with notified_at {notified_at}")
        else:
            await db.execute(
                "UPDATE waitlist SET status = ? WHERE id = ?",
                (status, waitlist_id)
            )
            if entry:
                logger.warning(f"Updated waitlist entry {waitlist_id} for user {entry['user_id']} and event {entry['event_id']} to status '{status}'")
            else:
                logger.warning(f"Updated waitlist entry {waitlist_id} to status '{status}'")

        await db.commit()

async def get_waitlist_entry(waitlist_id):
    """Get waitlist entry by ID."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM waitlist WHERE id = ?", (waitlist_id,))
        result = await cursor.fetchone()
        if result:
            logger.warning(f"Retrieved waitlist entry {waitlist_id} for user {result['user_id']} and event {result['event_id']} with status '{result['status']}'")
        else:
            logger.warning(f"Waitlist entry with ID {waitlist_id} not found")
        return result

async def get_user_waitlist(user_id):
    """Get all waitlist entries for a user."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            '''SELECT w.*, e.title, e.date FROM waitlist w 
               JOIN events e ON w.event_id = e.id 
               WHERE w.user_id = ? AND w.status = 'active' 
               ORDER BY e.date''',
            (user_id,)
        )
        result = await cursor.fetchall()
        logger.warning(f"Retrieved {len(result)} waitlist entries for user {user_id}")
        return result

async def get_event_waitlist(event_id, role=None):
    """Get all waitlist entries for an event, optionally filtered by role."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        if role:
            cursor = await db.execute(
                "SELECT * FROM waitlist WHERE event_id = ? AND role = ? AND status = 'active' ORDER BY added_at",
                (event_id, role)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM waitlist WHERE event_id = ? AND status = 'active' ORDER BY role, added_at",
                (event_id,)
            )

        result = await cursor.fetchall()
        if role:
            logger.warning(f"Retrieved {len(result)} waitlist entries for event {event_id} with role {role}")
        else:
            logger.warning(f"Retrieved {len(result)} waitlist entries for event {event_id}")
        return result

async def remove_from_waitlist(waitlist_id):
    """Remove a user from the waitlist."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        # First get the waitlist entry to check if it exists
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM waitlist WHERE id = ?", (waitlist_id,))
        waitlist_entry = await cursor.fetchone()

        if not waitlist_entry:
            logger.warning(f"Attempted to remove non-existent waitlist entry with ID {waitlist_id}")
            return False

        # Update status to removed
        await db.execute("UPDATE waitlist SET status = 'removed' WHERE id = ?", (waitlist_id,))
        await db.commit()

        logger.warning(f"Removed user {waitlist_entry['user_id']} from waitlist for event {waitlist_entry['event_id']} (waitlist ID: {waitlist_id})")
        return True

async def is_on_waitlist(event_id, user_id, role=None):
    """Check if a user is already on the waitlist for an event."""
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        if role:
            cursor = await db.execute(
                "SELECT 1 FROM waitlist WHERE event_id = ? AND user_id = ? AND role = ? AND status = 'active'",
                (event_id, user_id, role)
            )
        else:
            cursor = await db.execute(
                "SELECT 1 FROM waitlist WHERE event_id = ? AND user_id = ? AND status = 'active'",
                (event_id, user_id)
            )

        result = await cursor.fetchone()
        is_on_waitlist = bool(result)

        if role:
            logger.warning(f"Checked if user {user_id} is on waitlist for event {event_id} with role {role}: {is_on_waitlist}")
        else:
            logger.warning(f"Checked if user {user_id} is on waitlist for event {event_id}: {is_on_waitlist}")

        return is_on_waitlist

# Admin operations
async def add_admin(user_id):
    """Add a new admin."""
    async with aiosqlite.connect(DB_NAME) as db:
        added_at = datetime.now().isoformat()
        await db.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, added_at))
        await db.commit()

async def is_admin(user_id):
    """Check if a user is an admin."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return bool(result)

async def get_event_participants(event_id):
    """Get all participants for an event."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM registrations WHERE event_id = ? AND role = 'participant' AND status = 'active'",
            (event_id,)
        )
        return await cursor.fetchall()

async def get_event_speakers(event_id):
    """Get all speakers for an event."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM registrations WHERE event_id = ? AND role = 'speaker' AND status = 'active'",
            (event_id,)
        )
        return await cursor.fetchall()

async def get_expired_waitlist_notifications(expiration_time):
    """Get all expired waitlist notifications.

    Args:
        expiration_time (str): ISO format datetime string representing the expiration time

    Returns:
        list: List of expired waitlist entries
    """
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        # Find all expired waitlist notifications
        cursor = await db.execute(
            "SELECT * FROM waitlist WHERE status = 'notified' AND notified_at < ?",
            (expiration_time,)
        )
        expired_entries = await cursor.fetchall()

        logger.warning(f"Found {len(expired_entries)} expired waitlist notifications")
        return expired_entries

async def update_expired_waitlist_entry(entry_id):
    """Update the status of an expired waitlist entry to 'expired'.

    Args:
        entry_id (int): ID of the waitlist entry to update

    Returns:
        bool: True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            # Update status to expired
            await db.execute(
                "UPDATE waitlist SET status = 'expired' WHERE id = ?",
                (entry_id,)
            )
            await db.commit()
            logger.warning(f"Updated waitlist entry {entry_id} status to 'expired'")
            return True
        except Exception as e:
            logger.error(f"Failed to update waitlist entry {entry_id}: {str(e)}")
            return False

async def get_available_spots(event_id, role):
    """Get the number of available spots for a specific event and role.

    Args:
        event_id (int): ID of the event
        role (str): Role to check ('speaker' or 'participant')

    Returns:
        int: Number of available spots, or 0 if none available
    """
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        # Get event details to find max slots
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        event = await cursor.fetchone()

        if not event:
            logger.error(f"Event {event_id} not found when checking available spots")
            return 0

        # Get max slots based on role
        max_slots = event["max_speakers"] if role == "speaker" else event["max_participants"]

        # Count active registrations
        cursor = await db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND role = ? AND status = 'active'",
            (event_id, role)
        )
        active_count = (await cursor.fetchone())[0]

        # Calculate available spots
        available_spots = max(0, max_slots - active_count)
        logger.warning(f"Event {event_id} has {available_spots} available spots for role {role}")

        return available_spots

async def count_notified_waitlist_users(event_id, role):
    """Count the number of users in the waitlist with 'notified' status for a specific event and role.

    Args:
        event_id (int): ID of the event
        role (str): Role to check ('speaker' or 'participant')

    Returns:
        int: Number of notified users in the waitlist
    """
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM waitlist WHERE event_id = ? AND role = ? AND status = 'notified'",
            (event_id, role)
        )
        notified_count = (await cursor.fetchone())[0]
        logger.warning(f"Event {event_id} has {notified_count} notified users in waitlist for role {role}")
        return notified_count

async def count_active_waitlist_users(event_id, role):
    """Count the number of users in the waitlist with 'active' status for a specific event and role.

    Args:
        event_id (int): ID of the event
        role (str): Role to check ('speaker' or 'participant')

    Returns:
        int: Number of active users in the waitlist
    """
    logger = logging.getLogger(__name__)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM waitlist WHERE event_id = ? AND role = ? AND status = 'active'",
            (event_id, role)
        )
        active_count = (await cursor.fetchone())[0]
        logger.warning(f"Event {event_id} has {active_count} active users in waitlist for role {role}")
        return active_count

async def get_event_statistics(event_id):
    """Get statistics for an event."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Get event details
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        event = await cursor.fetchone()

        if not event:
            return None

        # Count active speakers
        cursor = await db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND role = 'speaker' AND status = 'active'",
            (event_id,)
        )
        speakers_count = (await cursor.fetchone())[0]

        # Count active participants
        cursor = await db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND role = 'participant' AND status = 'active'",
            (event_id,)
        )
        participants_count = (await cursor.fetchone())[0]

        # Count waitlist speakers
        cursor = await db.execute(
            "SELECT COUNT(*) FROM waitlist WHERE event_id = ? AND role = 'speaker' AND status = 'active'",
            (event_id,)
        )
        waitlist_speakers = (await cursor.fetchone())[0]

        # Count waitlist participants
        cursor = await db.execute(
            "SELECT COUNT(*) FROM waitlist WHERE event_id = ? AND role = 'participant' AND status = 'active'",
            (event_id,)
        )
        waitlist_participants = (await cursor.fetchone())[0]

        return {
            "event": dict(event),
            "speakers": {
                "active": speakers_count,
                "max": event["max_speakers"],
                "waitlist": waitlist_speakers
            },
            "participants": {
                "active": participants_count,
                "max": event["max_participants"],
                "waitlist": waitlist_participants
            }
        }
