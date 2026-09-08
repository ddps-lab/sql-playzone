"""
Plugin to automatically create Student ID Number field on CTFd startup
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from CTFd.models import UserFields, db
from CTFd.utils.student_ids import enforce_student_ids

STUDENT_ID_DESCRIPTION = (
    "HYU Student ID Number (e.g., 2025123456). "
    "Please enter your student ID number carefully. An incorrect ID may prevent us "
    "from matching your submissions and scores to you and processing your grade."
)

def load(app):
    """Initialize custom user fields for student registration"""
    app.config["UNIQUE_STUDENT_IDS"] = True
    if not event.contains(Session, "before_flush", enforce_student_ids):
        event.listen(Session, "before_flush", enforce_student_ids)
    
    with app.app_context():
        # Check if Student ID Number field already exists
        student_id_field = UserFields.query.filter_by(name="Student ID Number").first()
        
        if not student_id_field:
            # Create the Student ID Number field
            student_id_field = UserFields(
                name="Student ID Number",
                description=STUDENT_ID_DESCRIPTION,
                required=True,
                public=False,
                editable=True,
                field_type="text"
            )
            
            db.session.add(student_id_field)
            db.session.commit()
            print("[Student Fields Plugin] Created 'Student ID Number' field")
        else:
            # Update existing field to ensure correct settings
            updated = False
            if student_id_field.description != STUDENT_ID_DESCRIPTION:
                student_id_field.description = STUDENT_ID_DESCRIPTION
                updated = True
            if not student_id_field.required:
                student_id_field.required = True
                updated = True
            if student_id_field.public:
                student_id_field.public = False  
                updated = True
            if not student_id_field.editable:
                student_id_field.editable = True
                updated = True
            if student_id_field.field_type != "text":
                student_id_field.field_type = "text"
                updated = True
                
            if updated:
                db.session.commit()
                print("[Student Fields Plugin] Updated 'Student ID Number' field settings")
            else:
                print("[Student Fields Plugin] 'Student ID Number' field already configured correctly")
