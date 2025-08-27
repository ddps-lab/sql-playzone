import os
import sqlite3
import tempfile
import time
import subprocess
import atexit
import socket
from flask import Blueprint, request, jsonify
from CTFd.models import Challenges, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge, ChallengeResponse
from CTFd.utils.decorators import admins_only


class SQLChallenge(Challenges):
    __mapper_args__ = {"polymorphic_identity": "sql"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    init_query = db.Column(db.Text, default="")
    solution_query = db.Column(db.Text, default="")

    def __init__(self, *args, **kwargs):
        super(SQLChallenge, self).__init__(**kwargs)


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
        data = request.form or request.get_json()
        
        # Extract SQL-specific fields
        init_query = data.get("init_query", "")
        solution_query = data.get("solution_query", "")
        
        # Create challenge with base fields
        challenge = cls.challenge_model(**data)
        challenge.init_query = init_query
        challenge.solution_query = solution_query
        
        db.session.add(challenge)
        db.session.commit()
        
        return challenge

    @classmethod
    def read(cls, challenge):
        """
        Access the data of a SQL challenge.
        """
        challenge = SQLChallenge.query.filter_by(id=challenge.id).first()
        data = super().read(challenge)
        
        # Add SQL-specific fields
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
        
        # Update SQL-specific fields
        if "init_query" in data:
            challenge.init_query = data["init_query"]
        if "solution_query" in data:
            challenge.solution_query = data["solution_query"]
        
        # Update base fields
        for attr, value in data.items():
            if attr not in ["init_query", "solution_query"]:
                setattr(challenge, attr, value)
        
        db.session.commit()
        return challenge

    @classmethod
    def attempt(cls, challenge, request):
        """
        Check whether a given SQL query produces the correct result.
        """
        data = request.form or request.get_json()
        submission = data.get("submission", "").strip()
        
        if not submission:
            return ChallengeResponse(
                status="incorrect",
                message="Please provide a SQL query"
            )
        
        # Execute SQL queries using Go MySQL server
        try:
            import requests
            import json
            
            # Use Go MySQL server
            go_server_url = os.environ.get('SQL_JUDGE_SERVER_URL', 'http://localhost:8080')
            response = requests.post(
                f"{go_server_url}/judge",
                json={
                    'init_query': challenge.init_query,
                    'solution_query': challenge.solution_query,
                    'user_query': submission
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if not result.get('success'):
                    return ChallengeResponse(
                        status="incorrect",
                        message=f"Error: {result.get('error', 'Unknown error')}"
                    )
                
                # Format results for display
                user_result_str = json.dumps(result['user_result'])
                expected_result_str = json.dumps(result['expected_result'])
                
                if result['match']:
                    return ChallengeResponse(
                        status="correct",
                        message=f"✅ Correct! Your query produced the expected result.\n\n[USER_RESULT]\n{user_result_str}\n[/USER_RESULT]"
                    )
                else:
                    return ChallengeResponse(
                        status="incorrect",
                        message=f"❌ Incorrect. Your query did not produce the expected result.\n\n[USER_RESULT]\n{user_result_str}\n[/USER_RESULT]\n\n[EXPECTED_RESULT]\n{expected_result_str}\n[/EXPECTED_RESULT]"
                    )
            else:
                return ChallengeResponse(
                    status="incorrect",
                    message=f"SQL judge server error: HTTP {response.status_code}"
                )
                    
        except Exception as e:
            return ChallengeResponse(
                status="incorrect",
                message=f"Error executing query: {str(e)}"
            )

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
            # First, run go mod tidy to download dependencies and create go.sum
            print("Running go mod tidy to download dependencies...")
            mod_tidy = subprocess.run(
                ['go', 'mod', 'tidy'],
                cwd=plugin_dir,
                capture_output=True,
                text=True
            )
            if mod_tidy.returncode != 0:
                print(f"Failed to download dependencies: {mod_tidy.stderr}")
                print("Trying go mod download as fallback...")
                # Try go mod download as fallback
                mod_download = subprocess.run(
                    ['go', 'mod', 'download'],
                    cwd=plugin_dir,
                    capture_output=True,
                    text=True
                )
                if mod_download.returncode != 0:
                    print(f"Failed to download Go dependencies: {mod_download.stderr}")
                    return
            else:
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
    
    # Ensure the sql_challenge table exists
    with app.app_context():
        # Create table if it doesn't exist
        inspector = db.inspect(db.engine)
        if 'sql_challenge' not in inspector.get_table_names():
            db.create_all()
            print("Created sql_challenge table")
    
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