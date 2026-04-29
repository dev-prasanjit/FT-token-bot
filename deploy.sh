#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Tradetron Token Bot - VPS Deployment Script
# Run this ON the Oracle VPS after uploading the files
# ─────────────────────────────────────────────────────────────

set -e

echo "🚀 Deploying Tradetron Token Bot..."

# 1. Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install --user -r requirements.txt

# 2. Install Playwright + browser
echo "🌐 Installing Playwright Chromium..."
python3 -m playwright install chromium
sudo python3 -m playwright install-deps chromium

# 3. Create screenshots directory
mkdir -p screenshots

# 4. Test run
echo "🧪 Running test..."
python3 bot.py --now

echo ""
read -p "Did you receive the Telegram notification? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "❌ Fix the issue before proceeding."
    exit 1
fi

# 5. Install systemd service
echo "⚙️  Setting up systemd service..."
sudo cp tradetron-token-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tradetron-token-bot
sudo systemctl start tradetron-token-bot

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Useful commands:"
echo "   sudo systemctl status tradetron-token-bot   # Check status"
echo "   sudo systemctl restart tradetron-token-bot  # Restart bot"
echo "   sudo systemctl stop tradetron-token-bot     # Stop bot"
echo "   journalctl -u tradetron-token-bot -f        # View live logs"
echo "   tail -f ~/tradetron-token-bot/token_bot.log # View bot logs"
