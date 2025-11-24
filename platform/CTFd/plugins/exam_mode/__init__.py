from flask import Blueprint, render_template, request, redirect, url_for, session
from CTFd.models import db, Users, UserFieldEntries, UserFields, Configs
from CTFd.utils.decorators import admins_only
from CTFd.plugins import register_admin_plugin_menu_bar
from CTFd.utils import set_config, get_config

def load(app):
    # Register menu item
    register_admin_plugin_menu_bar(
        title='Exam Mode',
        route='/admin/exam_mode/'
    )

    # Create blueprint
    exam_mode = Blueprint(
        'exam_mode',
        __name__,
        template_folder='templates',
        url_prefix='/admin/exam_mode'
    )

    @exam_mode.route('/', methods=['GET'])
    @admins_only
    def index():
        enabled = get_config('exam_mode_enabled', False)
        allowed_ids = get_config('exam_mode_allowed_ids', '')
        return render_template('exam_mode_config.html', exam_mode_enabled=enabled, exam_mode_allowed_ids=allowed_ids)

    @exam_mode.route('/update', methods=['POST'])
    @admins_only
    def update_config():
        enabled = request.form.get('exam_mode_enabled') == 'on'
        allowed_ids_text = request.form.get('exam_mode_allowed_ids', '').strip()
        
        # Save config
        set_config('exam_mode_enabled', 'true' if enabled else 'false')
        set_config('exam_mode_allowed_ids', allowed_ids_text)

        # Parse allowed IDs
        allowed_ids = set(line.strip() for line in allowed_ids_text.splitlines() if line.strip())

        # Get Student ID field
        student_id_field = UserFields.query.filter_by(name="Student ID Number").first()
        
        if not student_id_field:
            # If field doesn't exist, we can't filter by it, so maybe just warn?
            # For now, let's assume it exists as per requirements.
            pass

        # Bulk update logic
        users = Users.query.filter_by(type='user').all()
        
        for user in users:
            should_ban = False
            
            if enabled:
                # Check if user has allowed student ID
                user_student_id = None
                if student_id_field:
                    entry = UserFieldEntries.query.filter_by(user_id=user.id, field_id=student_id_field.id).first()
                    if entry:
                        user_student_id = entry.value
                
                if user_student_id and user_student_id in allowed_ids:
                    should_ban = False
                else:
                    should_ban = True
            else:
                # If disabled, unban everyone (or revert to previous state? Requirement says unban)
                should_ban = False
            
            user.banned = should_ban

        db.session.commit()
        
        return redirect(url_for('exam_mode.index'))

    app.register_blueprint(exam_mode)
