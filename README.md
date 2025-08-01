# Marzban Admin Management Telegram Bot

A comprehensive Telegram bot built with Aiogram 3 for managing non-sudo admins in Marzban panel with smart monitoring and limit enforcement.

## Features

### Admin Management (Sudo Only)
- ➕ Add/Remove admins with custom limits
- 📊 Set user, time, and traffic limits per admin
- 📋 View all admins and their status
- 🔄 Activate/Deactivate admins

### Regular Admin Features
- 👤 View account information and current usage
- 📈 Get real-time usage reports
- 👥 View user list and statistics
- 🔄 Reactivate disabled users (when limits allow)
- ⚠️ Receive warnings at 80% limit usage

### Smart Monitoring System
- 🕐 Automatic monitoring every 10 minutes
- 🚫 Auto-disable users when limits exceeded
- 📨 Instant notifications to admins and sudo
- 📊 Detailed usage tracking and reporting
- 🔄 Allow reactivation when limits permit

### Security
- 🔐 Only registered admins can use the bot
- 👮 Sudo admins defined in configuration
- 🛡️ Full authorization checking
- 📝 Complete action logging

## Installation

1. Clone the repository:
```bash
git clone https://github.com/miladez1/sudomrzaadmun.git
cd sudomrzaadmun
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
export BOT_TOKEN="your_telegram_bot_token"
export MARZBAN_URL="https://your-marzban-panel.com"
export MARZBAN_USERNAME="admin"
export MARZBAN_PASSWORD="admin_password"
export SUDO_ADMINS="123456789,987654321"  # Comma-separated user IDs
```

4. Run the bot:
```bash
python bot.py
```

## Configuration

The bot uses environment variables for configuration. See `config.py` for all available options:

- `BOT_TOKEN`: Telegram bot token
- `MARZBAN_URL`: Marzban panel URL
- `MARZBAN_USERNAME`: Marzban admin username
- `MARZBAN_PASSWORD`: Marzban admin password
- `SUDO_ADMINS`: Comma-separated list of sudo admin user IDs
- `MONITORING_INTERVAL`: Monitoring check interval in seconds (default: 600)
- `WARNING_THRESHOLD`: Warning threshold percentage (default: 0.8 = 80%)

## Database Schema

The bot uses SQLite database with three main tables:

### admins
- User information and limits
- Usage tracking
- Status management

### usage_reports
- Historical usage data
- Periodic monitoring reports
- Trend analysis

### logs
- All admin actions
- System events
- Audit trail

## API Integration

The bot integrates with Marzban API to:
- Fetch user data and statistics
- Enable/disable users
- Monitor usage and limits
- Enforce restrictions

## Monitoring System

The smart monitoring system:
1. Checks all admin limits every 10 minutes
2. Sends warnings at 80% usage
3. Auto-disables users when limits exceeded
4. Sends notifications to relevant parties
5. Allows reactivation when limits permit

## Persian Language Support

The bot fully supports Persian (Farsi) language with:
- Persian messages and notifications
- Proper RTL text formatting
- Cultural date/time formats
- Localized number formatting

## Usage

### For Sudo Admins
1. Start the bot with `/start`
2. Use inline keyboard to manage admins
3. Add admins with custom limits
4. Monitor all admin activities

### For Regular Admins
1. Start the bot with `/start`
2. View your account limits and usage
3. Get real-time reports
4. Manage your users within limits

## License

This project is open source and available under the MIT License.

## Support

For support and bug reports, please create an issue on GitHub.