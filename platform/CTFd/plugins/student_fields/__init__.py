"""
Plugin to automatically create Student ID Number field on CTFd startup
"""

from CTFd.models import UserFields, db

def load(app):
    """Initialize custom user fields for student registration"""
    
    with app.app_context():
        # Check if Student ID Number field already exists
        student_id_field = UserFields.query.filter_by(name="Student ID Number").first()
        
        if not student_id_field:
            # Create the Student ID Number field
            student_id_field = UserFields(
                name="Student ID Number",
                description="HYU Student ID Number(ex:2025123456)",
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
            if student_id_field.description != "HYU Student ID Number(ex:2025123456)":
                student_id_field.description = "HYU Student ID Number(ex:2025123456)"
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