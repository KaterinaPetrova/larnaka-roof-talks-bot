# 🏢 Larnaka Roof Talks Bot

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Aiogram](https://img.shields.io/badge/Aiogram-3.0+-00bb00.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

<p align="center">
  <img src="https://img.shields.io/badge/🇨🇾Larnaka-🌌🎤Roof%20Talks-orange?style=for-the-badge" alt="Larnaka Roof Talks"/>
</p>

A powerful Telegram bot for managing Larnaka Roof Talks events, handling speaker and participant registrations, waitlists, and event notifications.

## ✨ Features

- **Event Management**
  - Create and manage community events
  - Set speaker and participant limits
  - Configure event details and schedules

- **Registration System**
  - Seamless registration for speakers and participants
  - Automatic waitlist when event is full
  - Payment confirmation workflow 

- **User Experience**
  - View and manage personal event registrations
  - Receive timely notifications and reminders
  - Cancel registrations with automatic waitlist promotion

- **Admin Controls**
  - Comprehensive admin panel
  - Real-time notifications for all registration activities
  - Manage users, events, and waitlists

## 🔧 Requirements

- Python 3.10+
- aiogram v3+
- aiosqlite
- python-dotenv
- APScheduler

## 🚀 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/RoofTalksBot.git
cd RoofTalksBot
```

2. **Create a virtual environment and install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment variables:**

   Create a `.env` file in the project root with:
```
BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id
NOTIFICATION_CHAT_ID=chat_id_for_notifications
```

   To get a chat ID:
   - For a private chat: Send a message to @userinfobot
   - For a group: Add @RawDataBot to the group, then remove it after getting the chat ID

## 💾 Database Setup

The bot automatically creates the SQLite database (`roof_talks.db`) with all required tables on first run.

To add an admin manually:
```sql
INSERT INTO admins (user_id, added_at) VALUES (your_telegram_user_id, datetime('now'));
```

## ▶️ Running the Bot

```bash
python main.py
```

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and show the main menu |
| `/myevents` | View your registrations |
| `/admin` | Access the admin panel (admin only) |
| `/help` | Show help information |
| `/cancel` | Cancel the current operation |

## 📁 Project Structure

```
RoofTalksBot/
├── main.py              # Entry point
├── config.py            # Configuration settings
├── database/            # Database operations
├── handlers/            # Command and callback handlers
├── states/              # FSM states
├── keyboards/           # UI keyboards
├── utils/               # Helper functions
├── tests/               # Test files
└── logs/                # Log files
```

## 📄 License

MIT

---

<p align="center">
  <i>This project was vibe-coded with Junie 🤖 by JetBrains.</i>
</p>
