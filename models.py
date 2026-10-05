# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON

db = SQLAlchemy()

class PatientChart(db.Model):
    __tablename__ = "patient_charts"

    id = db.Column(db.String(64), primary_key=True)
    patient_name = db.Column(db.String(128), nullable=False)

    # Sub-sections of the patient record
    vitals = db.Column(JSON, default=dict)
    allergies = db.Column(JSON, default=list)
    prescriptions = db.Column(JSON, default=list)
    clinical_notes = db.Column(JSON, default=dict)

    # Version Vector: tracks sequential edits per section
    version_vector = db.Column(JSON, nullable=False, default=lambda: {
        "vitals": 0,
        "allergies": 0,
        "prescriptions": 0,
        "clinical_notes": 0
    })

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)