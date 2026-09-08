"""
Plugin to automatically create Student ID Number field on CTFd startup
"""

from CTFd.models import UserFields, db

STUDENT_ID_DESCRIPTION = (
    "HYU Student ID Number(ex:2025123456). "
    "주의: 학번을 잘못 입력하면 제출 답안과 채점 결과를 본인에게 연결하지 못해 "
    "성적 처리가 어려워질 수 있습니다. 본인의 학번을 반드시 정확하게 입력해 주세요."
)

def load(app):
    """Initialize custom user fields for student registration"""
    
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