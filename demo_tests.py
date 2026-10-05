# demo_tests.py
import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000/api/v1/patients/pt-101"

def print_section(title):
    print("\n" + "=" * 70)
    print(f" TEST SUITE: {title}")
    print("=" * 70)

def print_result(label, resp):
    print(f"\n--> {label}")
    print(f"Status: {resp.status_code}")
    print(f"Payload:\n{json.dumps(resp.json(), indent=2)}")

# 0. Initial Baseline State
print_section("0. Fetch Initial Patient Record Baseline")
res = requests.get(BASE_URL)
print_result("Initial State & Vector Versions", res)

# 1. Pessimistic Lock Acquisition
print_section("1. Pessimistic Mutual Exclusion (Lease Acquisition)")
lock_payload = {"user_id": "dr_varun", "section": "clinical_notes"}
lock_res = requests.post(f"{BASE_URL}/lock", json=lock_payload)
print_result("Dr. Varun acquires lease on 'clinical_notes'", lock_res)
dr_token = lock_res.json().get("lock_token")

# 2. Pessimistic Collision
print_section("2. Pessimistic Contention / Mutex Collision")
conflict_payload = {"user_id": "nurse_smith", "section": "clinical_notes"}
conflict_res = requests.post(f"{BASE_URL}/lock", json=conflict_payload)
print_result("Nurse Smith attempts to acquire active lease (Blocked)", conflict_res)

# 3. Optimistic Update (Non-Conflicting Field)
print_section("3. Optimistic Concurrency Control (Version Vector Advance)")
opt_payload_1 = {
    "concurrency_mode": "optimistic",
    "version_vector": {"vitals": 0, "clinical_notes": 0, "allergies": 0, "prescriptions": 0},
    "updates": {"vitals": {"bp": "120/80", "hr": 74}}
}
opt_res_1 = requests.put(BASE_URL, json=opt_payload_1)
print_result("Independent edit committed to 'vitals' (Version increments to 1)", opt_res_1)

# 4. Optimistic Version Mismatch (Stale Write Detection)
print_section("4. Stale Write Conflict Detection (409)")
stale_payload = {
    "concurrency_mode": "optimistic",
    "version_vector": {"vitals": 0, "clinical_notes": 0, "allergies": 0, "prescriptions": 0},
    "updates": {"vitals": {"bp": "130/85", "hr": 80}}
}
stale_res = requests.put(BASE_URL, json=stale_payload)
print_result("Doctor B submits stale 'vitals: 0' while server is at '1' (Rejected)", stale_res)

# 5. Pessimistic Commit & Token Invalidation
print_section("5. Pessimistic Write Commit & Automatic Lease Release")
pess_update = {
    "concurrency_mode": "pessimistic",
    "lock_token": dr_token,
    "version_vector": {"clinical_notes": 0},
    "updates": {"clinical_notes": {"summary": "Reviewed chart; stable discharge plan."}}
}
commit_res = requests.put(BASE_URL, json=pess_update)
print_result("Dr. Varun commits update with token (Lease released)", commit_res)

# 6. Verify Lock Released
print_section("6. Verify Lock Availability Post-Commit")
verify_res = requests.post(f"{BASE_URL}/lock", json={"user_id": "nurse_smith", "section": "clinical_notes"})
print_result("Nurse Smith can now acquire 'clinical_notes'", verify_res)