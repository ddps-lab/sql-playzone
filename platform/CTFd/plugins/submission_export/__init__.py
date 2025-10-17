"""
Submission Export Plugin for CTFd
Allows admins to view and export submission status for all users
"""
import csv
from io import StringIO
from flask import Blueprint, render_template, Response
from CTFd.models import db, Users, Challenges, Solves, UserFieldEntries, UserFields
from CTFd.utils.decorators import admins_only
from CTFd.plugins import register_admin_plugin_menu_bar
from sqlalchemy import func


def load(app):
    """Load the submission export plugin"""

    # Register menu item in admin panel
    register_admin_plugin_menu_bar(
        title='Submission Export',
        route='/admin/submission_export/'
    )

    # Create blueprint for the plugin
    submission_export = Blueprint(
        'submission_export',
        __name__,
        template_folder='templates',
        static_folder='static',
        url_prefix='/admin/submission_export'
    )

    @submission_export.route('/')
    @admins_only
    def index():
        """Display submission status page"""
        # Get all challenges ordered by ID
        challenges = Challenges.query.order_by(Challenges.id).all()

        # Get all users with their information
        users = Users.query.filter_by(type='user', banned=False, hidden=False).order_by(Users.id).all()

        # Get Student ID Number field
        student_id_field = UserFields.query.filter_by(name="Student ID Number").first()

        # Build user data with submissions
        user_data = []
        for user in users:
            # Get student ID
            student_id = ""
            if student_id_field:
                student_id_entry = UserFieldEntries.query.filter_by(
                    user_id=user.id,
                    field_id=student_id_field.id
                ).first()
                if student_id_entry:
                    student_id = student_id_entry.value

            # Get solves for this user
            user_solves = {
                solve.challenge_id: solve
                for solve in Solves.query.filter_by(user_id=user.id).all()
            }

            # Build challenge scores
            challenge_scores = {}
            for challenge in challenges:
                if challenge.id in user_solves:
                    # Get the score (value) for the challenge
                    challenge_scores[challenge.id] = challenge.value or 0
                else:
                    challenge_scores[challenge.id] = 0

            user_data.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'student_id': student_id,
                'challenge_scores': challenge_scores
            })

        return render_template(
            'submission_export.html',
            users=user_data,
            challenges=challenges
        )

    @submission_export.route('/export.csv')
    @admins_only
    def export_csv():
        """Export submission data as CSV"""
        # Get all challenges ordered by ID
        challenges = Challenges.query.order_by(Challenges.id).all()

        # Get all users
        users = Users.query.filter_by(type='user', banned=False, hidden=False).order_by(Users.id).all()

        # Get Student ID Number field
        student_id_field = UserFields.query.filter_by(name="Student ID Number").first()

        # Create CSV in memory with UTF-8 BOM for Excel compatibility
        output = StringIO()
        # Write UTF-8 BOM for proper Korean encoding in Excel
        output.write('\ufeff')
        writer = csv.writer(output)

        # Write header
        header = ['Name', 'Email', 'Student ID']
        for challenge in challenges:
            header.append(f'{challenge.name} (ID: {challenge.id})')
        header.append('Total Score')
        writer.writerow(header)

        # Write user data
        for user in users:
            # Get student ID
            student_id = ""
            if student_id_field:
                student_id_entry = UserFieldEntries.query.filter_by(
                    user_id=user.id,
                    field_id=student_id_field.id
                ).first()
                if student_id_entry:
                    student_id = student_id_entry.value

            # Get solves for this user
            user_solves = {
                solve.challenge_id: solve
                for solve in Solves.query.filter_by(user_id=user.id).all()
            }

            # Build row with total score
            row = [user.name, user.email, student_id]
            total_score = 0
            for challenge in challenges:
                if challenge.id in user_solves:
                    score = challenge.value or 0
                    row.append(score)
                    total_score += score
                else:
                    row.append(0)
            row.append(total_score)

            writer.writerow(row)

        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': 'attachment; filename=submission_export.csv'
            }
        )

    # Register blueprint
    app.register_blueprint(submission_export)

    print("[Submission Export Plugin] Loaded successfully")
