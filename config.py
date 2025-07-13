import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot token from environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Database settings
DB_NAME = "roof_talks.db"

# Event statuses
EVENT_STATUS_OPEN = "open"
EVENT_STATUS_CLOSED = "closed"
EVENT_STATUS_COMPLETED = "completed"

# Registration statuses
REG_STATUS_ACTIVE = "active"
REG_STATUS_CANCELLED = "cancelled"
REG_STATUS_EXPIRED = "expired"

# Roles
ROLE_SPEAKER = "speaker"
ROLE_PARTICIPANT = "participant"

# Waitlist timeout in hours
WAITLIST_TIMEOUT_HOURS = 3

# Notification chat ID for admin updates
NOTIFICATION_CHAT_ID = os.getenv("NOTIFICATION_CHAT_ID")

# Revolut donation link
REVOLUT_DONATION_URL = os.getenv("REVOLUT_DONATION_URL")

# Backup chat ID for database exports
BACKUP_CHAT_ID = os.getenv("BACKUP_CHAT_ID")
