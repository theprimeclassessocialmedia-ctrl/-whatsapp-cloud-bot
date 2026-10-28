from flask import Flask, request, jsonify
import requests
from datetime import datetime

app = Flask(__name__)

# --- आपकी सेटिंग्स ---

ACCESS_TOKEN = "EAA6dqbdecDUBSzNcGPEPaa6DcoEeOrj7yoTxCYWIXbXiS1pFWv4qfdA9NAmtwYFq7ZCFCcf2dm8sqAjp25nrr67XZCTmjviAJie97ScwGdDdJRRniCW1oW8mx7czjCujcGhdiUZCfmZAgNiQnQUkqCZCtzoE8D1MotfQppAu14Ur9FAwHfkUESucYfHqQ2aj9Br0a0PdTtZAXl8vICPHz5YwYYEnR7hi5Le50LKV7gQQWoUpy3RTxsfAxBPCew6eZBl9fORb1urgNtotZAUHAtEznh09"

PHONE_NUMBER_ID = "1365015290033149"

VERIFY_TOKEN = "tpc_bot_123"

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbzo7QpzK5bHIbVhhXCLrlEzd0SxItRP4iO9oIbwjA2hYwVnpbMvfHDe6ZeodcLx0Jfl/exec"


def save_to_google_sheet(phone, name, ad_type, message):
    """Google Drive की शीट में डेटा अपने-आप जोड़ना"""
    try:
        payload = {
            "date": datetime.now().strftime("%d-%m-%Y"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "name": name,
            "phone": phone,
            "ad": ad_type,
            "message": message
        }
        requests.post(GOOGLE_SHEET_URL, json=payload, timeout=8)
    except Exception as e:
        print(f"Sheet Save Error: {e}")


def send_whatsapp_reply(to_phone, text):
    """WhatsApp पर मैसेज भेजना"""
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=payload)


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification token mismatch", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    try:
        if data.get("entry"):
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    val = change.get("value", {})
                    messages = val.get("messages", [])
                    contacts = val.get("contacts", [])

                    if messages:
                        msg = messages[0]
                        sender_phone = msg.get("from")
                        user_name = contacts[0].get("profile", {}).get(
                            "name", "विद्यार्थी/अभिभावक"
                        ) if contacts else "विद्यार्थी"

                        incoming_text = msg.get("text", {}).get("body", "")

                        # विज्ञापन (Ad Headline) ट्रैक करना
                        ad_headline = ""
                        if "referral" in msg:
                            ad_headline = msg["referral"].get("headline", "")

                        context = f"{incoming_text} {ad_headline}".lower()

                        # विज्ञापन के अनुसार स्मार्ट रिप्लाई
                        if any(k in context for k in [
                            "test series", "टेस्ट", "mock", "test"
                        ]):
                            ad_category = "Test Series Ad"
                            reply = (
                                f"नमस्ते {user_name} जी! 🙏\n\n"
                                "The Prime Classes की टेस्ट सीरीज़ में रुचि "
                                "दिखाने के लिए धन्यवाद।\n"
                                "हमारी ऑल-इंडिया टेस्ट सीरीज़ पूर्णतः "
                                "नवीनतम पैटर्न पर आधारित है।\n\n"
                                "आप किस कक्षा (कक्षा 6 या कक्षा 9) की "
                                "टेस्ट सीरीज़ चाहते हैं? कृपया रिप्लाई करें।"
                            )

                        elif any(k in context for k in [
                            "admission", "batch", "आरंभ", "aarambh", "class"
                        ]):
                            ad_category = "Admission / Course Ad"
                            reply = (
                                f"नमस्ते {user_name} जी! 🙏\n\n"
                                "The Prime Classes के 'आरंभ बैच' की जानकारी "
                                "के लिए धन्यवाद।\n"
                                "हमारे बैच में संपूर्ण सिलेबस की लाइव "
                                "कक्षाएं और नोट्स शामिल हैं।\n\n"
                                "हमारी टीम शीघ्र ही आपसे संपर्क करेगी। "
                                "कृपया अपना शहर और छात्र का नाम दर्ज करें।"
                            )

                        else:
                            ad_category = "सामान्य पूछताछ"
                            reply = (
                                f"नमस्ते {user_name} जी! 🙏\n\n"
                                "The Prime Classes में संपर्क करने के लिए धन्यवाद।\n"
                                "कृपया बताएँ आप किस प्रवेश परीक्षा "
                                "(Sainik School / RMS / RIMC) की जानकारी चाहते हैं?"
                            )

                        # 1. Google Drive की शीट में सेव करें
                        save_to_google_sheet(
                            sender_phone,
                            user_name,
                            ad_category,
                            incoming_text
                        )

                        # 2. WhatsApp ऑटो-रिप्लाई भेजें
                        send_whatsapp_reply(sender_phone, reply)

    except Exception as e:
        print(f"Webhook Error: {e}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(port=5000)
