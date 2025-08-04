import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("service-account.json")
firebase_admin.initialize_app(cred)

def send_fcm_notification(token: str, title: str, body: str, data: dict = None):
    print("📤 Sending FCM to:", token)
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=token,
        data=data or {},
    )
    try:
        response = messaging.send(message)
        print("✅ FCM sent:", response)
    except Exception as e:
        print("❌ Failed to send FCM:", e)

