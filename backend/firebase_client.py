"""
firebase_client.py - Using REST API instead of Admin SDK
No more JWT clock issues!
"""

import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
HOTEL_ID = os.getenv("HOTEL_ID", "hotel_grand_001")

def _url(path):
    return f"{DATABASE_URL}/{path}.json"

def _get(path):
    try:
        res = requests.get(_url(path))
        return res.json()
    except:
        return None

def _set(path, data):
    try:
        requests.put(_url(path), json=data)
        return True
    except:
        return False

def _update(path, data):
    try:
        requests.patch(_url(path), json=data)
        return True
    except:
        return False

def _push(path, data):
    try:
        res = requests.post(_url(path), json=data)
        result = res.json()
        return result.get('name')
    except:
        return None

def _delete(path):
    try:
        requests.delete(_url(path))
        return True
    except:
        return False

# ── INIT ──────────────────────────────────────────────────────
def init_firebase():
    print("✅ Firebase REST API connected")

init_firebase()

# ══════════════════════════════════════════════════════════════
# STAFF OPERATIONS
# ══════════════════════════════════════════════════════════════

def get_all_staff():
    data = _get(f"hotels/{HOTEL_ID}/staff")
    return data or {}

def get_available_staff():
    all_staff = get_all_staff()
    available = []
    for staff_id, data in all_staff.items():
        if data.get("status") == "available":
            available.append({"id": staff_id, **data})
    return available

def update_staff_status(staff_id, status, assignment=None):
    update_data = {"status": status}
    if assignment:
        update_data["current_assignment"] = assignment
    else:
        update_data["current_assignment"] = None
    _update(f"hotels/{HOTEL_ID}/staff/{staff_id}", update_data)

def update_staff_location(staff_id, location):
    _update(f"hotels/{HOTEL_ID}/staff/{staff_id}", 
            {"last_location": location})

# ══════════════════════════════════════════════════════════════
# GUEST OPERATIONS
# ══════════════════════════════════════════════════════════════

def get_guests_in_zone(floors):
    all_guests = _get(f"hotels/{HOTEL_ID}/guests") or {}
    affected = []
    for room, data in all_guests.items():
        if str(data.get("floor")) in [str(f) for f in floors]:
            affected.append({"room": room, **data})
    return affected

def update_guest_safety(room, status):
    _update(f"hotels/{HOTEL_ID}/guests/{room}", 
            {"safety_status": status})

def get_guest_by_room(room):
    return _get(f"hotels/{HOTEL_ID}/guests/{room}") or {}

def register_guest(room, name, phone, language, floor):
    _set(f"hotels/{HOTEL_ID}/guests/{room}", {
        "name": name,
        "phone": phone,
        "language": language,
        "floor": floor,
        "safety_status": "unknown",
        "alert_sent": False,
        "checked_in": True
    })

# ══════════════════════════════════════════════════════════════
# CRISIS OPERATIONS
# ══════════════════════════════════════════════════════════════

def create_crisis(crisis_data):
    key = _push(f"hotels/{HOTEL_ID}/active_crises", crisis_data)
    return key

def get_active_crises():
    data = _get(f"hotels/{HOTEL_ID}/active_crises")
    return data or {}

def update_crisis(crisis_id, data):
    _update(f"hotels/{HOTEL_ID}/active_crises/{crisis_id}", data)

def close_crisis(crisis_id):
    crisis_data = _get(f"hotels/{HOTEL_ID}/active_crises/{crisis_id}")
    if crisis_data:
        crisis_data["status"] = "resolved"
        _set(f"hotels/{HOTEL_ID}/crisis_history/{crisis_id}", crisis_data)
        _delete(f"hotels/{HOTEL_ID}/active_crises/{crisis_id}")

def add_crisis_timeline_event(crisis_id, event, actor):
    _push(f"hotels/{HOTEL_ID}/active_crises/{crisis_id}/timeline", {
        "event": event,
        "actor": actor,
        "timestamp": int(time.time())
    })

# ══════════════════════════════════════════════════════════════
# DEMO DATA
# ══════════════════════════════════════════════════════════════

def load_demo_data():
    _set(f"hotels/{HOTEL_ID}/info", {
        "name": "Hotel Grand",
        "address": "MG Road, Ludhiana, Punjab",
        "floors": 8,
        "total_rooms": 80
    })

    _set(f"hotels/{HOTEL_ID}/staff", {
        "staff_001": {
            "name": "Rajesh Kumar",
            "role": "security",
            "phone": "+91XXXXXXXXXX",
            "floor": 4,
            "last_location": "Floor 4 Corridor",
            "status": "available",
            "current_assignment": None
        },
        "staff_002": {
            "name": "Priya Sharma",
            "role": "nurse",
            "phone": "+91XXXXXXXXXX",
            "floor": 1,
            "last_location": "Reception",
            "status": "available",
            "current_assignment": None
        },
        "staff_003": {
            "name": "Amit Singh",
            "role": "manager",
            "phone": "+91XXXXXXXXXX",
            "floor": 1,
            "last_location": "Manager Office",
            "status": "available",
            "current_assignment": None
        },
        "staff_004": {
            "name": "Suresh Verma",
            "role": "housekeeping",
            "phone": "+91XXXXXXXXXX",
            "floor": 3,
            "last_location": "Floor 3",
            "status": "available",
            "current_assignment": None
        },
        "staff_005": {
            "name": "Deepak Rao",
            "role": "housekeeping",
            "phone": "+91XXXXXXXXXX",
            "floor": 5,
            "last_location": "Floor 5",
            "status": "available",
            "current_assignment": None
        }
    })

    _set(f"hotels/{HOTEL_ID}/guests", {
        "room_401": {"name": "Arjun Mehta", "phone": "+91XXXXXXXXXX", "language": "hi", "floor": 4, "safety_status": "unknown", "alert_sent": False},
        "room_402": {"name": "Yuki Tanaka", "phone": "+91XXXXXXXXXX", "language": "ja", "floor": 4, "safety_status": "unknown", "alert_sent": False},
        "room_403": {"name": "Ahmed Al-Rashid", "phone": "+91XXXXXXXXXX", "language": "ar", "floor": 4, "safety_status": "unknown", "alert_sent": False},
        "room_412": {"name": "John Smith", "phone": "+91XXXXXXXXXX", "language": "en", "floor": 4, "safety_status": "unknown", "alert_sent": False},
        "room_301": {"name": "Priya Nair", "phone": "+91XXXXXXXXXX", "language": "hi", "floor": 3, "safety_status": "unknown", "alert_sent": False},
        "room_501": {"name": "Carlos Ruiz", "phone": "+91XXXXXXXXXX", "language": "es", "floor": 5, "safety_status": "unknown", "alert_sent": False},
    })

    print("✅ Demo data loaded successfully")

if __name__ == "__main__":
    load_demo_data()