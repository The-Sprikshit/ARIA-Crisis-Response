from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import time
import os
from dotenv import load_dotenv

from gemini_engine import (
    classify_crisis,
    assign_staff_roles,
    generate_guest_alert,
    generate_responder_briefing,
    generate_crisis_analysis
)
from firebase_client import (
    get_available_staff,
    get_guests_in_zone,
    create_crisis,
    update_crisis,
    close_crisis,
    add_crisis_timeline_event,
    update_staff_status,
    update_guest_safety,
    get_active_crises,
    get_all_staff,
    register_guest,
    update_staff_location,
    init_firebase,
    _get, _set, _update, _delete, _push
)
from alert_sender import (
    send_staff_alert,
    send_bulk_guest_alerts,
    send_manager_alert,
    send_responder_briefing
)

load_dotenv()

# ── Single App Instance ───────────────────────────────────────────────────────
app = FastAPI(
    title="ARIA — Adaptive Response Intelligence for Hospitality",
    description="AI-powered emergency coordination system by THE_PHOENIX",
    version="1.0.0"
)

# ── Single CORS Middleware ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

HOTEL_ID = os.getenv("HOTEL_ID", "hotel_grand_001")


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════════════════════════════════════════

class CrisisReport(BaseModel):
    report: str
    reported_by: str
    reporter_location: Optional[str] = None

class GuestRegistration(BaseModel):
    room: str
    name: str
    phone: str
    language: str
    floor: int

class StaffLocationUpdate(BaseModel):
    staff_id: str
    location: str
    floor: int

class TaskStatusUpdate(BaseModel):
    staff_id: str
    crisis_id: str
    status: str

class GuestSafetyResponse(BaseModel):
    room: str
    crisis_id: str
    status: str

class CrisisClose(BaseModel):
    crisis_id: str
    resolved_by: str


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "system": "ARIA",
        "status": "operational",
        "team": "THE_PHOENIX",
        "members": ["Prikshit", "Mohit"]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": int(time.time())}


# ══════════════════════════════════════════════════════════════════════════════
# CRISIS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/crisis/report")
async def report_crisis(report: CrisisReport):
    start_time = time.time()

    # STEP 1: Classify with Gemini
    print(f"\n🧠 Classifying crisis: '{report.report}'")
    try:
        crisis = classify_crisis(report.report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini classification failed: {str(e)}")

    print(f"✅ Classified as: {crisis['crisis_type']} | Severity: {crisis['severity']}")

    # STEP 2: Create crisis in Firebase
    crisis_record = {
        **crisis,
        "reported_by": report.reported_by,
        "reporter_location": report.reporter_location or "Unknown",
        "status": "active",
        "created_at": int(time.time()),
        "staff_assignments": [],
        "guest_alerts_sent": 0,
        "guests_safe": 0,
        "guests_need_help": 0,
        "guests_unknown": 0
    }

    crisis_id = create_crisis(crisis_record)
    print(f"✅ Crisis created: {crisis_id}")

    add_crisis_timeline_event(
        crisis_id,
        f"Crisis reported: {crisis['crisis_type']} at {crisis['location']}",
        report.reported_by
    )

    # STEP 3: Get available staff
    available_staff = get_available_staff()
    print(f"✅ Available staff: {len(available_staff)}")

    # STEP 4: Assign roles
    assignments = []
    if available_staff:
        try:
            assignments = assign_staff_roles(crisis, available_staff)
        except Exception as e:
            print(f"⚠️ Role assignment failed: {e}")
            assignments = []

    # STEP 5: Update staff in Firebase
    staff_results = []
    for i, assignment in enumerate(assignments):
        assigned_id = assignment.get("staff_id")
        staff_info = next(
            (s for s in available_staff if s.get("id") == assigned_id),
            available_staff[i % len(available_staff)] if available_staff else None
        )

        if staff_info:
            real_id = staff_info.get("id", assigned_id)
            update_staff_status(real_id, "assigned", assignment["task"])
            add_crisis_timeline_event(
                crisis_id,
                f"Staff {assignment['name']} assigned: {assignment['task'][:50]}",
                "ARIA"
            )
            staff_results.append({
                "staff_id": real_id,
                "name": assignment.get("name", staff_info.get("name", "Staff")),
                "task": assignment["task"],
                "priority": assignment.get("priority", "HIGH")
            })

    update_crisis(crisis_id, {"staff_assignments": staff_results})
    print(f"✅ {len(staff_results)} staff assigned")

    # STEP 6: Get affected guests
    affected_guests = get_guests_in_zone(crisis.get("affected_floors", []))
    print(f"✅ Guests in zone: {len(affected_guests)}")

    # STEP 7: Send guest alerts
    guest_messages = {}
    for guest in affected_guests:
        room = guest.get("room")
        language = guest.get("language", "en")
        try:
            message = generate_guest_alert(crisis, language, room)
            guest_messages[room] = message
        except Exception as e:
            try:
                guest_messages[room] = generate_guest_alert(crisis, "en", room)
            except:
                pass

    alert_results = send_bulk_guest_alerts(affected_guests, guest_messages)
    update_crisis(crisis_id, {
        "guest_alerts_sent": alert_results["sent"],
        "guests_unknown": len(affected_guests)
    })

    add_crisis_timeline_event(
        crisis_id,
        f"Alerts sent: {alert_results['sent']} ok, {alert_results['failed']} failed",
        "ARIA"
    )

    # STEP 8: Alert manager
    all_staff = get_all_staff()
    manager = next(
        ({"phone": d["phone"], **d} for d in all_staff.values()
         if d.get("role") == "manager"),
        None
    )
    if manager:
        send_manager_alert(
            phone=manager["phone"],
            crisis_type=crisis["crisis_type"],
            severity=crisis["severity"],
            location=crisis["location"],
            staff_count=len(staff_results),
            guest_count=alert_results["sent"]
        )

    elapsed = round(time.time() - start_time, 2)
    print(f"\n✅ CRISIS COORDINATED in {elapsed}s")

    return {
        "crisis_id": crisis_id,
        "classification": crisis,
        "staff_assigned": len(staff_results),
        "guests_alerted": alert_results["sent"],
        "response_time_seconds": elapsed,
        "status": "active",
        "message": f"ARIA coordinated response in {elapsed}s"
    }


@app.get("/crisis/active")
def get_active():
    return get_active_crises()


@app.post("/crisis/close")
def close_active_crisis(data: CrisisClose):
    # Get crisis using REST API
    crisis_data = _get(f"hotels/{HOTEL_ID}/active_crises/{data.crisis_id}")

    if not crisis_data:
        raise HTTPException(status_code=404, detail="Crisis not found")

    crisis_data["resolved_at"] = int(time.time())
    crisis_data["resolved_by"] = data.resolved_by
    crisis_data["status"] = "resolved"

    # Generate learning analysis
    analysis = None
    try:
        analysis = generate_crisis_analysis(crisis_data)
        crisis_data["learning_analysis"] = analysis
    except Exception as e:
        print(f"⚠️ Analysis failed: {e}")

    # Move to history
    _set(f"hotels/{HOTEL_ID}/crisis_history/{data.crisis_id}", crisis_data)

    # Delete from active
    _delete(f"hotels/{HOTEL_ID}/active_crises/{data.crisis_id}")

    # Free all staff
    all_staff = get_all_staff()
    for staff_id in all_staff:
        update_staff_status(staff_id, "available")

    print(f"✅ Crisis {data.crisis_id} resolved")

    return {
        "status": "resolved",
        "crisis_id": data.crisis_id,
        "analysis": analysis
    }


# ══════════════════════════════════════════════════════════════════════════════
# STAFF ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/staff/all")
def get_staff():
    return get_all_staff()

@app.post("/staff/location")
def update_location(data: StaffLocationUpdate):
    update_staff_location(data.staff_id, data.location)
    return {"status": "updated", "staff_id": data.staff_id, "location": data.location}
class StaffRegistration(BaseModel):
    staff_id: str
    name: str
    role: str
    location: str = "Reception"

@app.post("/staff/register")
def register_staff(data: StaffRegistration):
    """Register new staff member or update existing."""
    from firebase_client import _set
    _set(f"hotels/{HOTEL_ID}/staff/{data.staff_id}", {
        "name": data.name,
        "role": data.role,
        "last_location": data.location,
        "status": "available",
        "current_assignment": None,
        "floor": 1,
        "phone": ""
    })
    return {"status": "registered", "staff_id": data.staff_id}

@app.post("/staff/task-status")
def update_task(data: TaskStatusUpdate):
    add_crisis_timeline_event(
        data.crisis_id,
        f"Staff {data.staff_id}: {data.status}",
        data.staff_id
    )
    if data.status == "completed":
        update_staff_status(data.staff_id, "available")
    return {"status": "updated"}


# ══════════════════════════════════════════════════════════════════════════════
# GUEST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/guest/register")
def register(data: GuestRegistration):
    register_guest(data.room, data.name, data.phone, data.language, data.floor)
    return {"status": "registered", "room": data.room}

@app.post("/guest/safety-response")
def guest_safety(data: GuestSafetyResponse):
    update_guest_safety(data.room, data.status)
    crises = get_active_crises()

    if data.crisis_id in crises:
        crisis = crises[data.crisis_id]
        if data.status == "safe":
            update_crisis(data.crisis_id, {
                "guests_safe": crisis.get("guests_safe", 0) + 1,
                "guests_unknown": max(0, crisis.get("guests_unknown", 1) - 1)
            })
        elif data.status == "needs_help":
            update_crisis(data.crisis_id, {
                "guests_need_help": crisis.get("guests_need_help", 0) + 1,
                "guests_unknown": max(0, crisis.get("guests_unknown", 1) - 1)
            })
            add_crisis_timeline_event(
                data.crisis_id,
                f"⚠️ Guest in {data.room} needs help!",
                "GUEST"
            )

    return {"status": "recorded", "room": data.room, "response": data.status}