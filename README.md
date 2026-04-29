# Tradetron Flattrade Token Bot 🤖

Automatically generates your daily Flattrade broker token on Tradetron every morning at **08:55 AM IST** and notifies you via Telegram.

## Features

- 🔐 Auto-login to Flattrade with TOTP (fully hands-free)
- ⏰ Scheduled daily at 08:55 AM IST (before market opens)
- 📱 Telegram notifications on success/failure
- 🎮 Manual trigger via Telegram `/generate` command
- 📸 Screenshots saved for debugging
- 📝 Full logging to `token_bot.log`

## Quick Setup

### 1. Install Dependencies

```bash
cd tradetron-token-bot
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

| Variable | Description |
|---|---|
| `FLATTRADE_USER_ID` | Your Flattrade client ID |
| `FLATTRADE_PASSWORD` | Your Flattrade password |
| `FLATTRADE_TOTP_SECRET` | TOTP secret key from authenticator setup |
| `TRADETRON_AUTH_URL` | Your Tradetron auth link (default is pre-filled) |
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

### 3. Get Your Telegram Bot Token & Chat ID

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow prompts, get your **Bot Token**
3. Start a chat with your new bot (send `/start`)
4. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in browser
5. Find your **chat ID** in the response JSON

### 4. Test It

```bash
# One-time test run (generates token immediately)
python bot.py --now

# Debug mode (shows browser window)
HEADLESS=false python bot.py --now
```

### 5. Run the Bot

```bash
# Foreground
python bot.py

# Background (Linux/Mac)
nohup python bot.py > /dev/null 2>&1 &

# Using screen
screen -S token-bot
python bot.py
# Ctrl+A, D to detach
```

## Telegram Commands

| Command | Description |
|---|---|
| `/generate` | Trigger token generation immediately |
| `/status` | Check if bot is running |

## Troubleshooting

- **Screenshots** are saved in the `screenshots/` folder after each attempt
- **Logs** are written to `token_bot.log`
- Set `HEADLESS=false` to watch the browser automation visually
- If TOTP fails, ensure your system clock is accurate (`ntpdate` or similar)
