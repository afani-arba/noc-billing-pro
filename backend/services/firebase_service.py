import os
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from typing import List, Optional

logger = logging.getLogger("firebase_service")

_firebase_initialized = False

def initialize_firebase():
    global _firebase_initialized
    if _firebase_initialized:
        return True

    # Cek apakah file JSON kredensial tersedia di repo atau via ENV
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-service-account.json")
    
    if os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info(f"Firebase Admin SDK initialized successfully using {cred_path}.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
            return False
    else:
        logger.warning(f"Firebase credentials not found at {cred_path}. Push notifications will be disabled.")
        return False

async def send_push_notification(tokens: List[str], title: str, body: str, data: Optional[dict] = None) -> bool:
    """Mengirim Push Notification ke daftar FCM tokens (Android/iOS/Web)"""
    if not tokens:
        return False
        
    if not _firebase_initialized:
        # Coba inisialisasi on-the-fly jika pertama kali digunakan
        if not initialize_firebase():
            return False

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="billing_alerts",
                    default_sound=True,
                    default_vibrate_timings=True
                )
            ),
            data=data or {},
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        logger.info(f"FCM batch sent: {response.success_count} success, {response.failure_count} failed")
        return response.success_count > 0
    except Exception as e:
        logger.error(f"FCM sending error: {e}")
        return False
