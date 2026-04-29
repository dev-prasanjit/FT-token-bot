"""
Tradetron Flattrade Token Generator Bot
========================================
Automatically generates the daily broker token for Flattrade via Tradetron
and sends Telegram notifications on success/failure.

Runs daily at 08:55 AM IST (before market opens at 09:15 AM).
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import pyotp
import requests
from playwright.async_api import async_playwright
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# ─── Load environment variables ──────────────────────────────────────────────
load_dotenv()

FLATTRADE_USER_ID = os.getenv("FLATTRADE_USER_ID")
FLATTRADE_PASSWORD = os.getenv("FLATTRADE_PASSWORD")
FLATTRADE_TOTP_SECRET = os.getenv("FLATTRADE_TOTP_SECRET")
TRADETRON_AUTH_URL = os.getenv(
    "TRADETRON_AUTH_URL",
    "https://flattrade.tradetron.tech/auth/823321",
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Indian Standard Time
IST = timezone(timedelta(hours=5, minutes=30))

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("token_bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("tradetron-token-bot")


# ─── Telegram helper ────────────────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    """Send a message to the configured Telegram chat. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set – skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            log.info("Telegram notification sent successfully.")
            return True
        else:
            log.error(f"Telegram API error {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        log.error(f"Telegram send failed: {exc}")
        return False


# ─── Token generation via Playwright ────────────────────────────────────────
async def generate_token() -> None:
    """
    Open the Flattrade auth page through Tradetron, fill in credentials
    and TOTP, submit the form, and detect success or failure.
    """
    log.info("=" * 60)
    log.info("Starting token generation…")
    now = datetime.now(IST)
    log.info(f"Current IST time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Pre-flight checks ────────────────────────────────────────────────
    missing = []
    if not FLATTRADE_USER_ID:
        missing.append("FLATTRADE_USER_ID")
    if not FLATTRADE_PASSWORD:
        missing.append("FLATTRADE_PASSWORD")
    if not FLATTRADE_TOTP_SECRET:
        missing.append("FLATTRADE_TOTP_SECRET")

    if missing:
        msg = f"❌ Missing credentials: {', '.join(missing)}. Cannot generate token."
        log.error(msg)
        send_telegram(f"🔴 <b>Tradetron Token FAILED</b>\n\n{msg}")
        return

    # Generate TOTP code
    totp = pyotp.TOTP(FLATTRADE_TOTP_SECRET)
    totp_code = totp.now()
    log.info(f"TOTP code generated: {totp_code[:2]}****")

    async with async_playwright() as p:
        browser = None
        try:
            # Launch browser (headless for server / headed for debugging)
            headless = os.getenv("HEADLESS", "true").lower() == "true"
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # ── Step 1: Navigate to Tradetron auth URL ───────────────────
            log.info(f"Navigating to {TRADETRON_AUTH_URL}")
            await page.goto(TRADETRON_AUTH_URL, wait_until="networkidle", timeout=30000)

            # Wait for the Flattrade login form to load
            log.info("Waiting for login form…")
            await page.wait_for_selector(
                'input[placeholder="User ID"], input[type="text"]',
                timeout=20000,
            )
            log.info("Login form detected.")

            # ── Step 2: Fill User ID ─────────────────────────────────────
            user_id_input = page.locator('input[placeholder="User ID"]')
            if await user_id_input.count() == 0:
                # Fallback: try the first text input
                user_id_input = page.locator('input[type="text"]').first
            await user_id_input.click()
            await user_id_input.fill(FLATTRADE_USER_ID)
            log.info("Filled User ID.")

            # ── Step 3: Fill Password ────────────────────────────────────
            password_input = page.locator('input[placeholder="Password"]')
            if await password_input.count() == 0:
                password_input = page.locator('input[type="password"]').first
            await password_input.click()
            await password_input.fill(FLATTRADE_PASSWORD)
            log.info("Filled Password.")

            # ── Step 4: Fill TOTP ────────────────────────────────────────
            totp_input = page.locator('input[placeholder="OTP / TOTP"]')
            if await totp_input.count() == 0:
                # Try other possible selectors
                totp_input = page.locator('input[placeholder*="TOTP"]').first
            if await totp_input.count() == 0:
                totp_input = page.locator('input[placeholder*="OTP"]').first

            await totp_input.click()
            await totp_input.fill(totp_code)
            log.info("Filled TOTP code.")

            # ── Step 5: Click Login ──────────────────────────────────────
            login_button = page.locator('button:has-text("Log In")')
            if await login_button.count() == 0:
                login_button = page.locator('button[type="submit"]')

            log.info("Clicking Login button…")
            await login_button.click()

            # ── Step 6: Wait for redirect / result ───────────────────────
            # After successful login, Flattrade redirects back to Tradetron
            # with a success message. We wait for either:
            #   - A redirect to tradetron.tech (success)
            #   - An error message on the login page (failure)
            log.info("Waiting for response…")

            import re
            try:
                # Wait for navigation away from auth.flattrade.in to tradetron
                await page.wait_for_url(
                    re.compile(r"tradetron\.tech"),
                    timeout=30000,
                )
                success = True
                log.info("Redirected to Tradetron — token generated!")
            except Exception:
                # Check if still on Flattrade page (login failed)
                current_url = page.url
                log.warning(f"No redirect detected. Current URL: {current_url}")

                # Try to grab error text from the page
                error_text = ""
                try:
                    error_el = page.locator(".v-alert, .error, .v-snack__content, .red--text, .text-danger, [class*='error']")
                    if await error_el.count() > 0:
                        # Get the most prominent error message
                        for i in range(await error_el.count()):
                            text = await error_el.nth(i).text_content()
                            if text and text.strip():
                                error_text = text.strip()
                                break
                except Exception:
                    pass

                # Fallback check
                if "tradetron.tech" in current_url.lower():
                    success = True
                    log.info("Redirected back to Tradetron domain — likely success.")
                else:
                    success = False
                    # Let's also check the body text just in case the error wasn't caught by locators
                    try:
                        body_text = await page.locator("body").text_content()
                        if not error_text and body_text:
                            if "invalid" in body_text.lower() or "blocked" in body_text.lower() or "wrong" in body_text.lower():
                                # Try to extract a reasonable chunk of text around the error
                                error_text = "Authentication failed (check screenshot for exact reason)"
                    except Exception:
                        pass
                    log.error(f"Token generation failed. Error: {error_text or 'Unknown'}")

            # ── Step 7: Take a screenshot for debugging ──────────────────
            screenshot_path = f"screenshots/token_{now.strftime('%Y%m%d_%H%M%S')}.png"
            os.makedirs("screenshots", exist_ok=True)
            await page.screenshot(path=screenshot_path, full_page=True)
            log.info(f"Screenshot saved: {screenshot_path}")

            # ── Step 8: Send Telegram notification ───────────────────────
            if success:
                msg = (
                    "🟢 <b>Tradetron Token Generated Successfully</b>\n\n"
                    f"📅 Date: {now.strftime('%d %b %Y')}\n"
                    f"⏰ Time: {now.strftime('%H:%M:%S')} IST\n"
                    f"🏦 Broker: Flattrade\n"
                    f"✅ Status: Token Active"
                )
                log.info("✅ Token generation SUCCESSFUL")
            else:
                msg = (
                    "🔴 <b>Tradetron Token Generation FAILED</b>\n\n"
                    f"📅 Date: {now.strftime('%d %b %Y')}\n"
                    f"⏰ Time: {now.strftime('%H:%M:%S')} IST\n"
                    f"🏦 Broker: Flattrade\n"
                    f"❌ Status: Failed\n"
                    f"📝 Details: Check logs and screenshot"
                )
                log.error("❌ Token generation FAILED")

            send_telegram(msg)

        except Exception as exc:
            error_msg = str(exc)
            log.exception(f"Unexpected error during token generation: {error_msg}")
            # Escape HTML special chars to avoid Telegram parse errors
            safe_error = (
                error_msg[:300]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            send_telegram(
                f"🔴 <b>Tradetron Token CRASHED</b>\n\n"
                f"📅 Date: {now.strftime('%d %b %Y')}\n"
                f"⏰ Time: {now.strftime('%H:%M:%S')} IST\n"
                f"💥 Error: <code>{safe_error}</code>"
            )
        finally:
            if browser:
                await browser.close()
                log.info("Browser closed.")

    log.info("=" * 60)


# ─── Manual trigger via Telegram command (optional) ──────────────────────────
async def check_telegram_commands() -> None:
    """
    Poll Telegram for /generate command to trigger manual token generation.
    This runs as a lightweight background task.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    last_update_id = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"

    while True:
        try:
            resp = requests.get(
                url,
                params={"offset": last_update_id + 1, "timeout": 10},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    message = update.get("message", {})
                    text = message.get("text", "")
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    if chat_id == TELEGRAM_CHAT_ID and text.strip() == "/generate":
                        log.info("Manual /generate command received from Telegram!")
                        send_telegram("⏳ Manual token generation triggered…")
                        await generate_token()
                    elif chat_id == TELEGRAM_CHAT_ID and text.strip() == "/status":
                        now = datetime.now(IST)
                        send_telegram(
                            f"🤖 <b>Bot Status: Running</b>\n"
                            f"⏰ Current Time: {now.strftime('%H:%M:%S')} IST\n"
                            f"📅 Date: {now.strftime('%d %b %Y')}\n"
                            f"⏭️ Next scheduled run: 08:55 AM IST"
                        )
        except Exception as exc:
            log.error(f"Telegram polling error: {exc}")

        await asyncio.sleep(3)


# ─── Main entry point ───────────────────────────────────────────────────────
async def main():
    log.info("🚀 Tradetron Token Bot starting…")
    log.info(f"Auth URL: {TRADETRON_AUTH_URL}")
    log.info(f"User ID: {FLATTRADE_USER_ID[:3]}***" if FLATTRADE_USER_ID else "User ID: NOT SET")
    log.info(f"Telegram configured: {bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)}")

    # Send startup notification
    now = datetime.now(IST)
    send_telegram(
        f"🤖 <b>Tradetron Token Bot Started</b>\n\n"
        f"⏰ Time: {now.strftime('%H:%M:%S')} IST\n"
        f"📅 Date: {now.strftime('%d %b %Y')}\n"
        f"⏭️ Scheduled run: 08:55 AM IST daily\n\n"
        f"Commands:\n"
        f"/generate - Trigger token generation now\n"
        f"/status - Check bot status"
    )

    # ── Set up scheduler ─────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        generate_token,
        CronTrigger(hour=8, minute=55, timezone="Asia/Kolkata"),
        id="daily_token_gen",
        name="Daily Flattrade Token Generation",
        misfire_grace_time=300,  # 5 min grace period
    )
    scheduler.start()
    log.info("Scheduler started — token generation at 08:55 AM IST daily.")

    # ── Run Telegram command listener in background ──────────────────────
    telegram_task = asyncio.create_task(check_telegram_commands())

    # ── Keep the bot alive ───────────────────────────────────────────────
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down…")
        scheduler.shutdown()
        telegram_task.cancel()


if __name__ == "__main__":
    # Allow running a one-time generation with: python bot.py --now
    if "--now" in sys.argv:
        log.info("Running one-time token generation (--now mode)…")
        asyncio.run(generate_token())
    else:
        asyncio.run(main())
