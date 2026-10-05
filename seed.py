# seed.py
from app import app
from models import db, PatientChart

with app.app_context():
    # 1. Create table schema in SQLite
    db.create_all()

    # 2. Seed test patient record
    existing = PatientChart.query.filter_by(id="pt-101").first()
    if not existing:
        patient = PatientChart(
            id="pt-101",
            patient_name="John Doe",
            vitals={"bp": "120/80", "hr": 72},
            allergies=["Penicillin"],
            prescriptions=[],
            clinical_notes={"summary": "Initial intake evaluation"},
            version_vector={
                "vitals": 0,
                "allergies": 0,
                "prescriptions": 0,
                "clinical_notes": 0
            }
        )
        db.session.add(patient)
        db.session.commit()
        print("Database initialized and pt-101 created successfully.")
    else:
        print("Record pt-101 already exists.")