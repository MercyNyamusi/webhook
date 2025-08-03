from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os
import requests
from dotenv import load_dotenv 


load_dotenv()

app = Flask(__name__)

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME")
MONGODB_COLLECTION_NAME = os.environ.get("MONGODB_COLLECTION_NAME")

print(f"PHONE_NUMBER_ID {PHONE_NUMBER_ID}")

client = MongoClient(MONGO_URI)
db = client["sasabot"]
sessions = db["chat_sessions"]
customers = db["customers"]
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
    business = businesses.find_one({"whatsapp_number": recipient_number})
    if not business:
        return jsonify({"error": "Business not found"}), 404

    business_id = business["_id"]

    # 🔍 Get or create customer from phone number
    customer = customers.find_one({"phone_number": phone_number})
    if not customer:
        customer_id = customers.insert_one({
            "phone_number": phone_number,
            "name": customer_name,
            "created_at": now()
        }).inserted_id
    else:
        customer_id = customer["_id"]

    session = sessions.find_one({
        "business_id": business_id,
        "customer_id": customer_id
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
            "customer_id": customer_id, 
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


@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    session_id = ObjectId(data['session_id'])
    print(f"session_id : {session_id}")
    text = data['text']

    session = sessions.find_one({"_id": session_id})
    if not session:
        return jsonify({"error": "Session not found"}), 404

    customer_id = session['customer_id']
    print(f"customer_id : {customer_id}")
    customer = customers.find_one({"_id": customer_id})

    if not customer or 'phone_number' not in customer:
        return jsonify({"error": "Customer phone not found"}), 404

    to_number = customer['phone_number'] 
    print(f"phone_number : {to_number}")
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

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        message_id = response.json().get("messages", [{}])[0].get("id")
        
        sessions.update_one(
            {"_id": session_id},
            {"$push": {
                "messages": {
                    "sender_type": "vendor",
                    "message_text": text,
                    "message_type": "text",
                    "timestamp": datetime.utcnow(),
                    "status": "sent",
                    "whatsapp_message_id": message_id
                }
            }}
        )

        return jsonify({"status": "Message sent", "message_id": message_id}), 200
    else:
        return jsonify({
            "error": "Failed to send message",
            "response": response.json()
        }), 500
