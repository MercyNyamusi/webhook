import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("service-account.json")
firebase_admin.initialize_app(cred)

def send_fcm_notifications(token: str, title: str, body: str, data=None):
    print("sending fcm notification to phone now")
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=token,
    )
    resp = messaging.send(message)
    print("FCM sent:", resp)
