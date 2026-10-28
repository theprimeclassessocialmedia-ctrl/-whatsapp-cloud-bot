import os
import logging
from datetime import datetime

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set these in Render -> Environment:
# ACCESS_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN, GOOGLE_SHEET_URL
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "").strip()
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "").strip()
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0").strip()


@app.get("/")
def home():
    return jsonify({
        "status": "running",
        "service": "WhatsApp Bot"
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/webhook")
def verify_webhook():
    """Meta webhook verification endpoint."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN and challenge:
        logger.info("Meta webhook verification successful")
        return challenge, 200

    logger.warning("Webhook verification request failed")
    return "Verification token mismatch", 403


def get_message_text(message):
    """Read text, button, and interactive list/button replies."""
    message_type = message.get("type", "")

    if message_type == "text":
        return message.get("text", {}).get("body", "")

    if message_type == "button":
        return message.get("button", {}).get("text", "")

    if message_type == "interactive":
        interactive = message.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        if button_reply:
            return button_reply.get("title") or button_reply.get("id", "")

        list_reply = interactive.get("list_reply", {})
        if list_reply:
            return list_reply.get("title") or list_reply.get("id", "")

    return ""


def save_to_google_sheet(phone, name, ad_type, message):
    """Send one incoming message row to the existing Apps Script endpoint."""
    if not GOOGLE_SHEET_URL:
        logger.error("GOOGLE_SHEET_URL is not configured")
        return False

    now = datetime.now().astimezone()
    payload = {
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%H:%M:%S"),
        "name": name,
        "phone": phone,
        "ad": ad_type,
        "message": message,
    }

    try:
        response = requests.post(GOOGLE_SHEET_URL, json=payload, timeout=15)
        logger.info("GOOGLE SHEET STATUS: %s", response.status_code)
        response.raise_for_status()
        return True
    except requests.RequestException:
        logger.exception("Google Sheet save failed")
        return False


def send_whatsapp_reply(to_phone, text):
    """Send a text reply using WhatsApp Cloud API and log Meta's response."""
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logger.error("ACCESS_TOKEN or PHONE_NUMBER_ID is not configured in Render")
        return False

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        logger.info("WHATSAPP REPLY STATUS: %s", response.status_code)
        # Response text contains Meta's API result/error; it should not contain your token.
        logger.info("WHATSAPP REPLY RESPONSE: %s", response.text)
        response.raise_for_status()
        return True
    except requests.RequestException:
        logger.exception("WhatsApp reply failed")
        return False


def create_reply(user_name, incoming_text, ad_headline=""):
    """Simple keyword-based replies; customize the text as needed."""
    context = f"{incoming_text} {ad_headline}".lower()

    if any(word in context for word in ("test series", "टेस्ट", "mock", "test")):
        category = "Test Series Ad"
        reply = (
            f"नमस्ते {user_name} जी! 🙏\n\n"
            "The Prime Classes की टेस्ट सीरीज़ में रुचि दिखाने के लिए धन्यवाद।\n"
            "आप किस कक्षा की टेस्ट सीरीज़ चाहते हैं?\n\n"
            "1. कक्षा 6\n"
            "2. कक्षा 9\n\n"
            "कृपया 1 या 2 लिखकर जवाब दें।"
        )
    elif any(word in context for word in (
        "admission", "batch", "आरंभ", "aarambh", "class", "एडमिशन", "फीस"
    )):
        category = "Admission / Course Ad"
        reply = (
            f"नमस्ते {user_name} जी! 🙏\n\n"
            "The Prime Classes में संपर्क करने के लिए धन्यवाद।\n"
            "आपको हमारे बैच और एडमिशन की जानकारी दी जाएगी।\n\n"
            "कृपया छात्र की कक्षा (6 या 9) और शहर का नाम बताएं।"
        )
    else:
        category = "सामान्य पूछताछ"
        reply = (
            f"नमस्ते {user_name} जी! 🙏\n\n"
            "The Prime Classes में आपका स्वागत है।\n"
            "आप किस परीक्षा की जानकारी चाहते हैं?\n\n"
            "1. Sainik School AISSEE\n"
            "2. RMS CET\n"
            "3. RIMC\n"
            "4. Navodaya\n\n"
            "कृपया परीक्षा का नाम या नंबर लिखें।"
        )

    return category, reply


@app.post("/webhook")
def receive_webhook():
    """Receive WhatsApp events from Meta."""
    data = request.get_json(silent=True) or {}

    if not data.get("entry"):
        logger.info("Webhook event received without entry data")
        return jsonify({"status": "received"}), 200

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                # Status updates (sent/delivered/read) have no messages array.
                if not messages:
                    continue

                contacts_by_wa_id = {
                    contact.get("wa_id"): contact
                    for contact in contacts
                    if contact.get("wa_id")
                }

                for message in messages:
                    sender_phone = message.get("from", "")
                    message_id = message.get("id", "")
                    if not sender_phone or not message_id:
                        logger.warning("Ignoring message without sender or message ID")
                        continue

                    incoming_text = get_message_text(message).strip()
                    contact = contacts_by_wa_id.get(sender_phone, {})
                    user_name = (
                        contact.get("profile", {}).get("name")
                        or "विद्यार्थी/अभिभावक"
                    )

                    referral = message.get("referral", {})
                    ad_headline = referral.get("headline", "")
                    category, reply = create_reply(
                        user_name, incoming_text, ad_headline
                    )

                    if referral:
                        category = "Click-to-WhatsApp Ad: " + (
                            ad_headline or "Referral received"
                        )

                    if incoming_text:
                        save_to_google_sheet(
                            sender_phone, user_name, category, incoming_text
                        )
                        send_whatsapp_reply(sender_phone, reply)
                    else:
                        logger.info(
                            "Received non-text message type=%s; no reply sent",
                            message.get("type", "unknown"),
                        )

    except Exception:
        logger.exception("Webhook processing error")

    # Acknowledge Meta so it does not repeatedly retry the same event.
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
