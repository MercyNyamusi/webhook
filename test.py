from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os
import requests

app = Flask(__name__)

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME")
MONGODB_COLLECTION_NAME=os.environ.get("MONGODB_COLLECTION_NAME")

client = MongoClient(MONGO_URI)
db = client[MONGODB_DB_NAME]
sessions = db["chat_sessions"]

businesses = db['businesses']


def now():
    return datetime.utcnow()



@app.route('/webhook/whatsapp', methods=['GET'])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


# Receive message
@app.route('/webhook/whatsapp', methods=['POST'])
def receive_message():
    data = request.json
    entry = data.get("entry", [])[0]
    changes = entry.get("changes", [])[0]
    value = changes.get("value", {})

    contacts = value.get("contacts", [])
    messages_data = value.get("messages", [])

    if not contacts or not messages_data:
        return jsonify({"message": "No contacts or messages"}), 200

    phone_number = contacts[0]['wa_id']
    customer_name = contacts[0].get("profile", {}).get("name", "Unknown")
    message = messages_data[0]
    text = message.get("text", {}).get("body", "")
    timestamp = datetime.utcfromtimestamp(int(message['timestamp']))

    metadata = value.get("metadata", {})
    recipient_number = metadata.get("display_phone_number")
    business = businesses.find_one({"phone_number": recipient_number})
    if not business:
        return jsonify({"error": "Business not found"}), 404

    business_id = business["_id"]

    session = sessions.find_one({
        "business_id": business_id,
        "customer_id": phone_number
    })

    message_data = {
        "_id": ObjectId(),  
        "sender_type": "user",
        "message_text": text,
        "message_type": "text",
        "timestamp": timestamp,
        "status": "sent"
    }

    if not session:
        session_id = sessions.insert_one({
            "business_id": business_id,
            "customer_id": phone_number,
            "customer_name": customer_name,
            "is_handled_by_vendor": False,
            "notifications_enabled": True,
            "unread_count": 1,
            "last_message": text,
            "last_message_time": timestamp,
            "botEnabled": True,
            "created_at": now(),
            "updated_at": now(),
            "messages": [message_data]
        }).inserted_id
    else:
        session_id = session['_id']
        sessions.update_one({"_id": session_id}, {
            "$set": {
                "last_message": text,
                "last_message_time": timestamp,
                "updated_at": now(),
                "botEnabled": True
            },
            "$inc": {"unread_count": 1},
            "$push": {"messages": message_data}
        })

    return jsonify({"status": "message saved"}), 200


# Message Status Updates
@app.route('/webhook/whatsapp/status', methods=['POST'])
def update_message_status():
    data = request.json
    entry = data.get("entry", [])[0]
    changes = entry.get("changes", [])[0]
    value = changes.get("value", {})
    statuses = value.get("statuses", [])

    for status in statuses:
        msg_id = status.get("id")
        msg_status = status.get("status")
        timestamp = datetime.utcfromtimestamp(int(status['timestamp']))

        sessions.update_many(
            {"messages._id": ObjectId(msg_id)},
            {"$set": {
                "messages.$.status": msg_status,
                "messages.$.timestamp": timestamp
            }}
        )

    return jsonify({"status": "updated"}), 200


# Send Message from Vendor to Customer
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    session_id = ObjectId(data['session_id'])
    text = data['text']

    session = sessions.find_one({"_id": session_id})
    if not session:
        return jsonify({"error": "Session not found"}), 404

    to_number = session['customer_id']
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }

    response = requests.post(url, json=payload, headers=headers)
    if not response.ok:
        return jsonify({"error": response.text}), 500

    res_json = response.json()
    msg_id = res_json.get("messages", [{}])[0].get("id", None)
    timestamp = now()

    message_record = {
        "_id": ObjectId(msg_id) if msg_id else ObjectId(),
        "sender_type": "vendor",
        "message_text": text,
        "message_type": "text",
        "timestamp": timestamp,
        "status": "sent"
    }

    sessions.update_one({"_id": session_id}, {
        "$set": {
            "last_message": text,
            "last_message_time": timestamp,
            "updated_at": timestamp,
            "is_handled_by_vendor": True
        },
        "$push": {"messages": message_record}
    })

    return jsonify({"status": "message sent", "message_id": msg_id}), 200



if __name__ == '__main__':
    app.run(debug=True, port=5000)
