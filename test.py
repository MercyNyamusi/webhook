from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_ID = os.getenv("WHATSAPP_ID")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

@app.route("/whatsapp/message", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and verify_token == VERIFY_TOKEN:
            print("✅ Webhook verified successfully.")
            return challenge, 200
        print("❌ Webhook verification failed.")
        return "Verification failed", 403

    elif request.method == "POST":
        data = request.get_json()
        print("📥 Incoming WhatsApp webhook payload:")
        print(data)

        try:
            entry = data["entry"][0]
            changes = entry["changes"][0]["value"]
            messages = changes.get("messages", [])

            if messages:
                message = messages[0]
                customer_phone = message["from"]
                message_text = message["text"]["body"]
                print(f"📩 Message from {customer_phone}: {message_text}")

                send_message(customer_phone, "Thanks for your message! We'll get back to you shortly.")
        except Exception as e:
            print(f"❌ Error handling message: {e}")

        return "EVENT_RECEIVED", 200


def send_message(customer_phone_number: str, text: str) -> bool:
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": customer_phone_number,
        "type": "text",
        "text": {"body": text}
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"➡️ Sent response: [{response.status_code}]: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return False


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
