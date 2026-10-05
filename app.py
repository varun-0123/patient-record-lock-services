# app.py
import os
import redis
from flask import Flask, request, jsonify
from models import db, PatientChart
from lock_manager import DistributedLockManager

app = Flask(__name__)

# SQLite local database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///patient_records.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Redis client initialization (defaulting to localhost:6379)
# Redis client with seamless local fakeredis fallback
try:
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=0
    )
    redis_client.ping()
except Exception:
    import fakeredis
    redis_client = fakeredis.FakeRedis()

lock_mgr = DistributedLockManager(redis_client, default_ttl_ms=30000)

# --- LOCK ROUTES ---

@app.route("/api/v1/patients/<patient_id>/lock", methods=["POST"])
def acquire_lock(patient_id):
    data = request.get_json() or {}
    user_id = data.get("user_id")
    section = data.get("section")

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    token = lock_mgr.acquire_pessimistic(patient_id, user_id, section=section)
    if not token:
        holder = lock_mgr.get_lock_holder(patient_id, section=section)
        return jsonify({
            "status": "conflict",
            "message": f"Section '{section or 'chart'}' is currently locked by {holder}",
            "locked_by": holder
        }), 409

    return jsonify({"status": "acquired", "lock_token": token, "ttl_ms": 30000}), 200

@app.route("/api/v1/patients/<patient_id>/lock/heartbeat", methods=["POST"])
def heartbeat(patient_id):
    data = request.get_json() or {}
    token = data.get("lock_token")
    section = data.get("section")

    if not token:
        return jsonify({"error": "lock_token required"}), 400

    if not lock_mgr.renew_pessimistic(patient_id, token, section=section):
        return jsonify({"status": "lost", "message": "Lock expired or usurped"}), 410

    return jsonify({"status": "renewed", "ttl_ms": 30000}), 200

# --- UPDATE ROUTE (OPTIMISTIC & PESSIMISTIC SUPPORT) ---

@app.route("/api/v1/patients/<patient_id>", methods=["PUT"])
def update_patient_chart(patient_id):
    data = request.get_json() or {}
    updates = data.get("updates", {})
    mode = data.get("concurrency_mode", "optimistic")
    lock_token = data.get("lock_token")
    client_vector = data.get("version_vector", {})

    chart = PatientChart.query.filter_by(id=patient_id).first()
    if not chart:
        return jsonify({"error": "Patient not found"}), 404

    modified_sections = list(updates.keys())

    # 1. Pessimistic check
    if mode == "pessimistic":
        if not lock_token:
            return jsonify({"error": "lock_token required for pessimistic mode"}), 400
        # Release the lock upon successful commit
        target_section = modified_sections[0] if len(modified_sections) == 1 else None
        if not lock_mgr.release_pessimistic(patient_id, lock_token, section=target_section):
            return jsonify({"error": "Lock invalid, not owned, or expired"}), 423

    # 2. Optimistic check with Version Vectors
    is_valid, err_msg, next_vector = lock_mgr.validate_and_advance_vector(
        chart.version_vector, client_vector, modified_sections
    )
    if not is_valid:
        return jsonify({
            "error": "CONCURRENT_CONFLICT",
            "message": err_msg,
            "current_version_vector": chart.version_vector
        }), 409

    # 3. Apply updates
    for sec, payload in updates.items():
        if hasattr(chart, sec):
            setattr(chart, sec, payload)

    chart.version_vector = next_vector
    db.session.commit()

    return jsonify({
        "status": "success",
        "version_vector": chart.version_vector,
        "updated_sections": modified_sections
    }), 200

@app.route("/api/v1/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id):
    chart = PatientChart.query.filter_by(id=patient_id).first()
    if not chart:
        return jsonify({"error": "Patient not found"}), 404

    return jsonify({
        "id": chart.id,
        "name": chart.patient_name,
        "vitals": chart.vitals,
        "allergies": chart.allergies,
        "prescriptions": chart.prescriptions,
        "clinical_notes": chart.clinical_notes,
        "version_vector": chart.version_vector,
        "updated_at": chart.updated_at.isoformat()
    }), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)