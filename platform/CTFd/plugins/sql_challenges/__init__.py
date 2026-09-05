import os
import sqlite3
import tempfile
import time
import subprocess
import atexit
import socket
from datetime import datetime, timezone
import pytz
from flask import Blueprint, request, jsonify, abort
from CTFd.models import Challenges, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge, ChallengeResponse
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.user import get_ip, is_admin

# Set KST timezone
KST = pytz.timezone('Asia/Seoul')


class SQLChallenge(Challenges):
    __mapper_args__ = {"polymorphic_identity": "sql"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    init_query = db.Column(db.Text, default="")
    solution_query = db.Column(db.Text, default="")
    deadline_utc = db.Column("deadline", db.DateTime, nullable=True)

    def __init__(self, *args, **kwargs):
        super(SQLChallenge, self).__init__(**kwargs)

    @property
    def deadline(self):
        """Return deadline in KST format for display in forms"""
        if self.deadline_utc is None:
            return None

        import logging
        logging.debug(f"[deadline getter] deadline_utc={self.deadline_utc}, type={type(self.deadline_utc)}")

        try:
            # Handle case where deadline_utc might be a string (shouldn't happen but let's be defensive)
            if isinstance(self.deadline_utc, str):
                logging.warning(f"[deadline getter] deadline_utc is unexpectedly a string: {self.deadline_utc}")
                # Try to parse it as a datetime
                try:
                    from datetime import datetime as dt
                    if 'T' in self.deadline_utc:
                        parsed_dt = dt.fromisoformat(self.deadline_utc.replace('Z', '+00:00'))
                    else:
                        parsed_dt = dt.fromisoformat(self.deadline_utc)
                    # Use the parsed datetime
                    utc_dt = parsed_dt.replace(tzinfo=pytz.UTC) if parsed_dt.tzinfo is None else parsed_dt.astimezone(pytz.UTC)
                except Exception as parse_error:
                    logging.error(f"[deadline getter] Failed to parse string deadline: {parse_error}")
                    return self.deadline_utc  # Return as-is
            else:
                # Normal case: deadline_utc is a datetime object
                utc_dt = self.deadline_utc.replace(tzinfo=pytz.UTC)

            kst_dt = utc_dt.astimezone(KST)
            # Return as ISO format string in KST for datetime-local input
            result = kst_dt.strftime('%Y-%m-%dT%H:%M')
            logging.debug(f"[deadline getter] Converted to KST string: {result}")
            return result
        except Exception as e:
            logging.error(f"[deadline getter] Error: {e}, deadline_utc={self.deadline_utc}, type={type(self.deadline_utc)}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    @deadline.setter
    def deadline(self, value):
        """Store deadline as naive UTC in database"""
        if value is None or value == '':
            self.deadline_utc = None
        elif isinstance(value, str):
            # Coming from form as KST string
            try:
                if 'T' in value:
                    naive_dt = datetime.fromisoformat(value)
                else:
                    naive_dt = datetime.fromisoformat(value.replace(' ', 'T'))
                # Localize to KST
                kst_dt = KST.localize(naive_dt) if naive_dt.tzinfo is None else naive_dt
                # Convert to UTC for storage
                utc_dt = kst_dt.astimezone(pytz.UTC)
                # Store as naive UTC
                self.deadline_utc = utc_dt.replace(tzinfo=None)
            except Exception as e:
                raise ValueError("Invalid deadline; use an ISO date and time") from e
        elif isinstance(value, datetime):
            # Coming from code as datetime object (assume naive UTC)
            self.deadline_utc = value.astimezone(pytz.UTC).replace(tzinfo=None) if value.tzinfo else value
        else:
            raise ValueError("Invalid deadline; use an ISO date and time")


class SQLChallengeType(BaseChallenge):
    id = "sql"
    name = "sql"
    templates = {
        "create": "/plugins/sql_challenges/assets/create.html",
        "update": "/plugins/sql_challenges/assets/update.html",
        "view": "/plugins/sql_challenges/assets/view.html",
    }
    scripts = {
        "create": f"/plugins/sql_challenges/assets/create.js?v={int(time.time())}",
        "update": f"/plugins/sql_challenges/assets/update.js?v={int(time.time())}",
        "view": f"/plugins/sql_challenges/assets/view.js?v={int(time.time())}",
    }
    route = "/plugins/sql_challenges/assets/"
    blueprint = Blueprint(
        "sql_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = SQLChallenge

    @classmethod
    def create(cls, request):
        """
        Process the challenge creation request for SQL challenges.
        """
        from CTFd.models import Flags
        data = request.form or request.get_json()
        
        # Extract SQL-specific fields
        init_query = data.get("init_query", "")
        solution_query = data.get("solution_query", "")
        deadline_str = data.get("deadline", "")

        # Remove fields that don't belong to the base model
        data.pop("flag", None)
        data.pop("flag_type", None)
        data.pop("init_query", None)
        data.pop("solution_query", None)
        data.pop("deadline", None)

        # Create challenge with base fields
        challenge = cls.challenge_model(**data)
        challenge.init_query = init_query
        challenge.solution_query = solution_query
        # deadline setter property will handle the KST->UTC conversion automatically
        try:
            challenge.deadline = deadline_str if deadline_str else None
        except ValueError as error:
            abort(400, description=str(error))
        
        db.session.add(challenge)
        db.session.commit()
        
        # Add a placeholder flag for SQL challenges
        # SQL challenges don't use traditional flags, but CTFd might expect at least one
        flag = Flags(
            challenge_id=challenge.id,
            type="static",
            content="[SQL_CHALLENGE_PLACEHOLDER]",
            data=""
        )
        db.session.add(flag)
        db.session.commit()
        
        return challenge

    @classmethod
    def read(cls, challenge):
        """
        Access the data of a SQL challenge.
        """
        challenge = SQLChallenge.query.filter_by(id=challenge.id).first()
        data = super().read(challenge)

        # The deadline property automatically converts UTC to KST format
        data["deadline"] = challenge.deadline
        # The init and solution SQL are the answer key. CTFd returns this dict
        # from the challenge detail API to every logged-in user, so only admins
        # may receive them.
        if is_admin():
            data.update({
                "init_query": challenge.init_query,
                "solution_query": challenge.solution_query,
            })

        return data

    @classmethod
    def update(cls, challenge, request):
        """
        Update the information associated with a SQL challenge.
        """
        data = request.form or request.get_json()
        
        if "deadline" in data:
            try:
                challenge.deadline = data["deadline"]
            except ValueError as error:
                abort(400, description=str(error))
        if "init_query" in data:
            challenge.init_query = data["init_query"]
        if "solution_query" in data:
            challenge.solution_query = data["solution_query"]

        # Update base fields
        for attr, value in data.items():
            if attr not in ["init_query", "solution_query", "deadline"]:
                setattr(challenge, attr, value)
        
        db.session.commit()
        return challenge

    @classmethod
    def attempt(cls, challenge, request):
        """Only a completed comparison or explicit student SQL error is graded."""
        import json
        import requests
        from CTFd.utils.user import get_current_user

        data = request.form or request.get_json()
        submission = data.get("submission", "").strip()
        is_test = data.get("test", False)
        user = get_current_user()
        prefix = "[TEST]\n" if is_test else ""
        unavailable = ChallengeResponse(
            status="error",
            message=prefix + "Grading is temporarily unavailable. No attempt was deducted. Please retry.",
        )
        try:
            response = requests.post(
                os.environ.get('SQL_JUDGE_SERVER_URL', 'http://localhost:8080') + '/judge',
                json={
                    'init_query': challenge.init_query,
                    'solution_query': challenge.solution_query,
                    'user_query': submission,
                    'user_id': str(user.id),
                    'user_name': user.name,
                    'client_ip': get_ip(),
                    'challenge_id': str(challenge.id),
                },
                timeout=10,
            )
            if response.status_code != 200:
                return unavailable
            result = response.json()
            if not isinstance(result, dict):
                return unavailable
            if result.get('success') is False:
                if result.get('error_kind') == 'student_query':
                    return ChallengeResponse(status="incorrect", message=prefix + str(result.get('error', 'SQL query failed')))
                # Older judges and unknown error kinds fail without a penalty.
                # Never expose reference-query or infrastructure errors to students.
                return unavailable
            if result.get('success') is not True or not isinstance(result.get('match'), bool):
                return unavailable
            for key in ('user_result', 'expected_result'):
                rows = result.get(key)
                if not isinstance(rows, dict) or not isinstance(rows.get('rows'), list) or not isinstance(rows.get('columns'), list):
                    return unavailable
            user_result = json.dumps(result['user_result'])
            if result['match']:
                return ChallengeResponse(
                    status="correct",
                    message=prefix + f"✅ Correct! Your query produced the expected result.\n\n[USER_RESULT]\n{user_result}\n[/USER_RESULT]",
                )
            expected = json.dumps(result['expected_result'])
            return ChallengeResponse(
                status="incorrect",
                message=prefix + f"❌ Incorrect. Your query did not produce the expected result.\n\n[USER_RESULT]\n{user_result}\n[/USER_RESULT]\n\n[EXPECTED_RESULT]\n{expected}\n[/EXPECTED_RESULT]",
            )
        except (requests.RequestException, ValueError, TypeError, KeyError):
            return unavailable

    @classmethod
    def execute_and_compare_with_details(cls, init_query, solution_query, user_query):
        """
        Execute queries and return detailed results for comparison.
        """
        import json
        expected_result = None
        user_result = None
        
        # First, get expected result
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path1 = tmp_file.name
        
        try:
            conn = sqlite3.connect(db_path1)
            cursor = conn.cursor()
            
            # Execute initialization query
            if init_query:
                for statement in init_query.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                conn.commit()
            
            # Execute solution query
            cursor.execute(solution_query)
            expected_result = cursor.fetchall()
            expected_columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
        finally:
            try:
                os.unlink(db_path1)
            except:
                pass
        
        # Now get user result in a fresh database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path2 = tmp_file.name
        
        try:
            conn = sqlite3.connect(db_path2)
            cursor = conn.cursor()
            
            # Execute initialization query again
            if init_query:
                for statement in init_query.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                conn.commit()
            
            # Execute user query
            cursor.execute(user_query)
            user_result = cursor.fetchall()
            user_columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
        finally:
            try:
                os.unlink(db_path2)
            except:
                pass
        
        # Format results as JSON for table rendering
        def format_result_json(columns, rows):
            return json.dumps({
                'columns': columns,
                'rows': [[str(cell) if cell is not None else "NULL" for cell in row] for row in rows],
                'row_count': len(rows)
            })
        
        return {
            'match': expected_result == user_result,
            'user_result_str': format_result_json(user_columns, user_result),
            'expected_result_str': format_result_json(expected_columns, expected_result)
        }
    
    @classmethod
    def execute_and_compare(cls, init_query, solution_query, user_query):
        """
        Execute queries in a temporary SQLite database and compare results.
        """
        expected_result = None
        user_result = None
        
        # First, get expected result
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path1 = tmp_file.name
        
        try:
            conn = sqlite3.connect(db_path1)
            cursor = conn.cursor()
            
            # Execute initialization query
            if init_query:
                for statement in init_query.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                conn.commit()
            
            # Execute solution query
            cursor.execute(solution_query)
            expected_result = cursor.fetchall()
            conn.close()
        finally:
            try:
                os.unlink(db_path1)
            except:
                pass
        
        # Now get user result in a fresh database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path2 = tmp_file.name
        
        try:
            conn = sqlite3.connect(db_path2)
            cursor = conn.cursor()
            
            # Execute initialization query again
            if init_query:
                for statement in init_query.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                conn.commit()
            
            # Execute user query
            cursor.execute(user_query)
            user_result = cursor.fetchall()
            conn.close()
        finally:
            try:
                os.unlink(db_path2)
            except:
                pass
        
        # Compare results
        return expected_result == user_result

    @classmethod
    def test_query(cls, init_query, test_query):
        """
        Test a query and return its result.
        Used for testing in the admin interface.
        """
        try:
            import requests
            
            # Use Go MySQL server for testing
            go_server_url = os.environ.get('SQL_JUDGE_SERVER_URL', 'http://localhost:8080')
            
            # We need to execute the test query and get its result
            # Use the judge endpoint with the test query as both solution and user query
            response = requests.post(
                f"{go_server_url}/judge",
                json={
                    'init_query': init_query,
                    'solution_query': test_query,  # Use test query as solution
                    'user_query': test_query  # And as user query to get the result
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('success'):
                    # Extract the result from user_result
                    user_result = result.get('user_result', {})
                    return {
                        "success": True,
                        "columns": user_result.get('columns', []),
                        "rows": user_result.get('rows', [])
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('error', 'Unknown error')
                    }
            else:
                return {
                    "success": False,
                    "error": f"Server returned status {response.status_code}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Global variable to store the Go server process
go_server_process = None

def is_port_open(host, port):
    """Check if a port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

def start_go_server():
    """Start the Go SQL judge server."""
    global go_server_process

    if not os.environ.get('MYSQL_ROOT_PASSWORD'):
        print("SQL Judge requires MYSQL_ROOT_PASSWORD and a reachable MySQL 8.4 server. Use Docker Compose or configure both before starting CTFd.")
        return
    
    # Check if server is already running
    if is_port_open('localhost', 8080):
        print("SQL Judge server already running on port 8080")
        return
    
    # Get the plugin directory path
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    server_binary = os.path.join(plugin_dir, 'sql-judge-server')
    
    # Check if binary exists, if not try to build it
    if not os.path.exists(server_binary):
        print("SQL Judge server binary not found, attempting to build...")
        try:
            # Download the versions locked by go.mod and go.sum without modifying them.
            print("Downloading SQL Judge dependencies...")
            mod_download = subprocess.run(
                ['go', 'mod', 'download'],
                cwd=plugin_dir,
                capture_output=True,
                text=True
            )
            if mod_download.returncode != 0:
                print(f"Failed to download Go dependencies: {mod_download.stderr}")
                return
            print("Dependencies downloaded successfully")
            
            # Now build the server
            print("Building SQL Judge server...")
            build_result = subprocess.run(
                ['go', 'build', '-o', 'sql-judge-server', 'sql_judge_server.go'],
                cwd=plugin_dir,
                capture_output=True,
                text=True
            )
            if build_result.returncode != 0:
                print(f"Failed to build SQL Judge server: {build_result.stderr}")
                print("Make sure Go is installed and dependencies are available")
                return
            print("SQL Judge server built successfully")
        except FileNotFoundError:
            print("Go is not installed. Please install Go or use Docker Compose")
            return
    
    # Start the server
    try:
        go_server_process = subprocess.Popen(
            [server_binary],
            cwd=plugin_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        import time
        for i in range(10):
            if is_port_open('localhost', 8080):
                print("SQL Judge server started successfully on port 8080")
                break
            time.sleep(0.5)
        else:
            print("SQL Judge server failed to start within 5 seconds")
            
    except Exception as e:
        print(f"Failed to start SQL Judge server: {e}")

def stop_go_server():
    """Stop the Go SQL judge server."""
    global go_server_process
    if go_server_process:
        print("Stopping SQL Judge server...")
        go_server_process.terminate()
        try:
            go_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            go_server_process.kill()
        go_server_process = None

def load(app):
    """Load the SQL challenge plugin."""
    from CTFd.plugins.migrations import upgrade
    
    # Upgrade database to include SQL challenge tables
    upgrade()
    
    # Ensure the sql_challenge table exists with all required columns
    with app.app_context():
        # Create table if it doesn't exist
        inspector = db.inspect(db.engine)
        if 'sql_challenge' not in inspector.get_table_names():
            db.create_all()
            print("Created sql_challenge table")
        else:
            # Check if deadline column exists, if not add it
            columns = [col['name'] for col in inspector.get_columns('sql_challenge')]
            if 'deadline' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text("ALTER TABLE sql_challenge ADD COLUMN deadline DATETIME NULL"))
                    conn.commit()
                print("Added deadline column to sql_challenge table")
    
    # Start the Go SQL judge server
    if not os.environ.get('SQL_JUDGE_SERVER_URL'):
        # Only start if not using external server
        start_go_server()
        atexit.register(stop_go_server)
    
    # Register challenge type
    CHALLENGE_CLASSES["sql"] = SQLChallengeType
    
    # Register assets directory
    register_plugin_assets_directory(app, base_path="/plugins/sql_challenges/assets/")
    
    # Add API endpoint for testing SQL queries
    @app.route('/api/v1/challenges/test-sql', methods=['POST'])
    @admins_only
    def test_sql_query():
        """API endpoint for testing SQL queries in admin interface"""
        data = request.get_json()
        init_query = data.get('init_query', '')
        test_query = data.get('test_query', '')

        if not test_query:
            return jsonify({
                'success': False,
                'error': 'No test query provided'
            }), 400

        result = SQLChallengeType.test_query(init_query, test_query)
        return jsonify(result)

    # Add API endpoint for getting SQL challenge submission history
    @app.route('/api/v1/challenges/<int:challenge_id>/sql-submissions', methods=['GET'])
    @authed_only
    def get_sql_submissions(challenge_id):
        """API endpoint for getting submission history for SQL challenges"""
        from CTFd.utils.user import get_current_user
        from CTFd.models import Submissions

        # Verify this is a SQL challenge
        challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()
        if challenge.type != "sql":
            return jsonify({
                'success': False,
                'error': 'Not a SQL challenge'
            }), 400

        # Get current user
        user = get_current_user()
        if not user:
            return jsonify({
                'success': False,
                'error': 'User not authenticated'
            }), 401

        # Get submissions for this user and challenge
        submissions = Submissions.query.filter_by(
            challenge_id=challenge_id,
            account_id=user.account_id
        ).order_by(Submissions.date.desc()).limit(50).all()

        # Format submissions for response
        submission_list = []
        for sub in submissions:
            # Ensure UTC timezone is explicit in the ISO format
            date_str = None
            if sub.date:
                # CTFd stores dates in UTC without timezone info
                # We need to explicitly mark it as UTC
                if sub.date.tzinfo is None:
                    # Add UTC timezone
                    utc_date = sub.date.replace(tzinfo=pytz.UTC)
                else:
                    # Already has timezone, ensure it's UTC
                    utc_date = sub.date.astimezone(pytz.UTC)

                # Return ISO format with explicit timezone (will have +00:00 suffix)
                date_str = utc_date.isoformat()

            submission_list.append({
                'id': sub.id,
                'date': date_str,
                'submission': sub.provided,
                'type': sub.type,  # 'correct' or 'incorrect'
            })

        return jsonify({
            'success': True,
            'data': submission_list
        })
