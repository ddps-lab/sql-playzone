from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from CTFd.models import db, Users, UserFieldEntries, UserFields, Configs, Files
from CTFd.utils.decorators import admins_only
from CTFd.plugins import register_admin_plugin_menu_bar
from CTFd.utils import set_config, get_config
from CTFd.utils.user import is_admin

# Exam browser restriction. When enabled, everyone except admins must use a
# browser whose User-Agent contains the marker (Trustlock's UA looks like
# "... Trustlockbrowser/2.1.1 Chrome/124.0.6367.207 Safari/537.36 CMAC 1.0001;").
# The User-Agent header can be forged, so this is a deterrent, not a proof.
DEFAULT_EXAM_BROWSER_MARKER = 'Trustlockbrowser'
EXAM_BROWSER_MESSAGE = (
    'During the exam this site is only available through the exam browser (Trustlock). '
    '시험 중에는 시험 전용 브라우저(Trustlock)에서만 접속할 수 있습니다.'
)
# Requests that must keep working from any browser: admins log in (or
# recover their password) from a normal browser, and the load balancer
# health check has no User-Agent.
# Uploaded files any page may need: logo, banner, page images. Challenge and
# solution attachments are not among them.
SITE_ASSET_FILE_TYPES = ('standard', 'page')
EXAM_BROWSER_EXEMPT_ENDPOINTS = {
    'auth.login',
    'auth.logout',
    'auth.reset_password',
    'auth.confirm',
    'views.themes',
    'views.themes_beta',
    'views.healthcheck',
    'static',
}


def exam_browser_required():
    # get_config turns the stored 'true'/'false' strings into booleans
    return get_config('exam_browser_required') is True


def exam_browser_marker():
    return (get_config('exam_browser_marker') or DEFAULT_EXAM_BROWSER_MARKER).strip()


def is_exam_browser(user_agent):
    return exam_browser_marker().lower() in (user_agent or '').lower()


def exam_browser_exempt():
    if request.endpoint in EXAM_BROWSER_EXEMPT_ENDPOINTS:
        return True
    if request.endpoint == 'views.files':
        # Uploaded files serve both site assets, which the login and error
        # pages need, and challenge or solution attachments, which must not
        # be fetched from another browser.
        upload = Files.query.filter_by(location=request.view_args.get('path')).first()
        return upload is None or upload.type in SITE_ASSET_FILE_TYPES
    return False


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
        return render_template(
            'exam_mode_config.html',
            exam_mode_enabled=enabled,
            exam_mode_allowed_ids=allowed_ids,
            exam_browser_required=exam_browser_required(),
            exam_browser_marker=exam_browser_marker(),
        )

    @exam_mode.route('/browser', methods=['POST'])
    @admins_only
    def update_browser():
        # A separate form on purpose: saving the exam mode form above rewrites
        # every user's banned flag, and this toggle must not trigger that.
        required = request.form.get('exam_browser_required') == 'on'
        marker = request.form.get('exam_browser_marker', '').strip() or DEFAULT_EXAM_BROWSER_MARKER
        set_config('exam_browser_required', 'true' if required else 'false')
        set_config('exam_browser_marker', marker)
        return redirect(url_for('exam_mode.index'))

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

    @app.before_request
    def require_exam_browser():
        if not exam_browser_required() or exam_browser_exempt():
            return
        if is_admin() or is_exam_browser(request.user_agent.string):
            return
        if request.is_json or request.path.startswith('/api/'):
            response = jsonify({'success': False, 'errors': [EXAM_BROWSER_MESSAGE]})
            response.status_code = 403
            return response
        return render_template('errors/403.html', error=EXAM_BROWSER_MESSAGE), 403
