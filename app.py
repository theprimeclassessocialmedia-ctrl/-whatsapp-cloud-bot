
import os
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Render Environment Variables se settings
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "").strip()
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "").strip()
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0").strip()


def save_to_google_sheet(phone, name, ad_type, message):
    """Incoming message ko Google Sheet mein save kare."""
    if not GOOGLE_SHEET_URL:
        logging.error("GOOGLE_SHEET_URL is missing")
        return False

    now = datetime.now(timezone.utc).astimezone()

    payload = {
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%H:%M:%S"),
        "name": name,
        "phone": phone,
        "ad": ad_type,
        "message": message
    }

    try:
        response = requests.post(
            GOOGLE_SHEET_URL,
            json=payload,
            timeout=15
        )

        logging.info(
            "GOOGLE SHEET STATUS: %s",
            response.status_code
        )
        response.raise_for_status()
        return True

    except requests.RequestException as e:
        logging.error("Google Sheet save failed: %s", str(e))
        return False


def send_whatsapp_reply(to_phone, text):
    """WhatsApp Cloud API se reply bheje."""
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logging.error("ACCESS_TOKEN or PHONE_NUMBER_ID is missing")
        return False

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        logging.info(
            "WHATSAPP REPLY STATUS: %s",
            response.status_code
        )
        logging.info(
            "WHATSAPP REPLY RESPONSE: %s",
            response.text
        )

        response.raise_for_status()
        return True

    except requests.RequestException as e:
        logging.error("WhatsApp reply failed: %s", str(e))
        return False


def get_message_text(message):
    """Text aur interactive button/list replies ko samjhe."""
    msg_type = message.get("type", "")

    if msg_type == "text":
        return message.get("text", {}).get("body", "")

    if msg_type == "button":
        return message.get("button", {}).get("text", "")

    if msg_type == "interactive":
        interactive = message.get("interactive", {})

        button_reply = interactive.get("button_reply", {})
        if button_reply:
            return (
                button_reply.get("title")
                or button_reply.get("id", "")
            )

        list_reply = interactive.get("list_reply", {})
        if list_reply:
            return (
                list_reply.get("title")
                or list_reply.get("id", "")
            )

    return ""


def create_reply(user_name, incoming_text, ad_headline=""):
    """Keyword ke hisaab se automatic reply banaye."""
    context = f"{incoming_text} {ad_headline}".lower()

    if any(k in context for k in [
        "test series", "टेस्ट", "mock", "test"
    ]):
        category = "Test Series Ad"
        reply = (
            f"नमस्ते {user_name} जी! 🙏\n\n"
            "The Prime Classes की टेस्ट सीरीज़ में रुचि "
            "दिखाने के लिए धन्यवाद।\n"
            "आप किस कक्षा की टेस्ट सीरीज़ चाहते हैं?\n\n"
            "1. कक्षा 6\n"
            "2. कक्षा 9\n\n"
            "कृपया 1 या 2 लिखकर जवाब दें।"
        )

    elif any(k in context for k in [
        "admission", "batch", "आरंभ", "aarambh", "class",
        "एडमिशन", "फीस"
    ]):
        category = "Admission / Course Ad"
        reply = (
            f"नमस्ते {user_name} जी! 🙏\n\n"
            "The Prime Classes में संपर्क करने के लिए धन्यवाद।\n"
            "आपको हमारे आरंभ बैच और एडमिशन की जानकारी "
            "दी जाएगी।\n\n"
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


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "service": "WhatsApp Bot"
    }), 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta webhook verification."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if (
        mode == "subscribe"
        and VERIFY_TOKEN
        and token == VERIFY_TOKEN
        and challenge
    ):
        logging.info("Webhook verification successful")
        return challenge, 200

    logging.warning("Webhook verification failed")
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """Meta se incoming WhatsApp events receive kare."""
    data = request.get_json(silent=True) or {}

    if not data.get("entry"):
        logging.info("Webhook event received without message entries")
        return jsonify({"status": "received"}), 200

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Delivery/read status events ko reply na karein.
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                if not messages:
                    continue

                contact_map = {
                    c.get("wa_id"): c
                    for c in contacts
                    if c.get("wa_id")
                }

                for message in messages:
                    sender_phone = message.get("from", "")
                    message_id = message.get("id", "")
                    message_type = message.get("type", "")

                    if not sender_phone or not message_id:
                        logging.warning(
                            "Message missing sender or message ID"
                        )
                        continue

                    incoming_text = get_message_text(message).strip()

                    contact = contact_map.get(sender_phone, {})
                    profile = contact.get("profile", {})
                    user_name = (
                        profile.get("name")
                        or "विद्यार्थी/अभिभावक"
                    )

                    # Ad referral information, if available
                    referral = message.get("referral", {})
                    ad_headline = referral.get("headline", "")

                    if referral:
                        ad_category = (
                            "Click-to-WhatsApp Ad: "
                            + (ad_headline or "Referral received")
                        )
                    else:
                        ad_category = "सामान्य पूछताछ"

                    logging.info(
                        "Incoming message received; type=%s",
                        message_type
                    )

                    if not incoming_text:
                        logging.info(
                            "Non-text message received; no auto-reply"
                        )
                        continue

                    keyword_category, reply = create_reply(
                        user_name,
                        incoming_text,
                        ad_headline
                    )

                    if not referral:
                        ad_category = keyword_category

                    # 1. Save incoming message to Google Sheet
                    save_to_google_sheet(
                        sender_phone,
                        user_name,
                        ad_category,
                        incoming_text
                    )

                    # 2. Send automatic WhatsApp reply
                    send_whatsapp_reply(
                        sender_phone,
                        reply
                    )

    except Exception:
        logging.exception("Webhook processing error")

    # Meta ko acknowledgement bhejein
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
