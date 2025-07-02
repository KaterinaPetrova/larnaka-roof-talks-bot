# Larnaka Roof Talks Bot

Telegram bot for managing Larnaka Roof Talks events, speakers, and participants.

## Features

- Event registration for speakers and participants
- Waitlist management
- User event management (view, edit, cancel)
- Admin panel for event management
- Notifications for registrations, waitlist, and reminders
- Admin notifications for all participant and speaker changes

## Requirements

- Python 3.10+
- aiogram v3+
- aiosqlite
- python-dotenv
- APScheduler

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/RoofTalksBot.git
cd RoofTalksBot
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with your Telegram bot token and other settings:
```
BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id  # Optional: Initial admin user ID
NOTIFICATION_CHAT_ID=chat_id_for_notifications  # Chat ID for admin notifications
```

To get a chat ID:
- For a private chat: Send a message to @userinfobot
- For a group: Add @RawDataBot to the group, then remove it after getting the chat ID

## Database Setup

The bot automatically creates the SQLite database (`roof_talks.db`) with the required tables on first run.

To add an admin, you can use the following SQL command:
```sql
INSERT INTO admins (user_id, added_at) VALUES (your_telegram_user_id, datetime('now'));
```

## Running the Bot

```bash
python main.py
```

## Bot Commands

- `/start` - Start the bot and show the main menu
- `/myevents` - View your registrations
- `/admin` - Access the admin panel (admin only)
- `/help` - Show help information
- `/cancel` - Cancel the current operation

## Project Structure

- `main.py` - Entry point
- `config.py` - Configuration settings
- `database/` - Database operations
- `handlers/` - Command and callback handlers
- `states/` - FSM states
- `keyboards/` - UI keyboards
- `utils/` - Helper functions
- `tests/` - Test files

## Testing

The project includes tests for the registration flow. To run the tests:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run the tests
pytest tests/test_registration.py -v
```

Alternatively, you can use the provided script:

```bash
./run_tests.sh
```

For more information about the tests, see the [tests/README.md](tests/README.md) file.

## License

MIT
