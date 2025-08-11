import os
import sqlite3
import tempfile
import time
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
        
        # Execute SQL queries in isolated environment
        try:
            result_data = cls.execute_and_compare_with_details(
                challenge.init_query,
                challenge.solution_query,
                submission
            )
            
            if result_data['match']:
                return ChallengeResponse(
                    status="correct",
                    message=f"✅ Correct! Your query produced the expected result.\n\n[USER_RESULT]\n{result_data['user_result_str']}\n[/USER_RESULT]"
                )
            else:
                return ChallengeResponse(
                    status="incorrect",
                    message=f"❌ Incorrect. Your query did not produce the expected result.\n\n[USER_RESULT]\n{result_data['user_result_str']}\n[/USER_RESULT]\n\n[EXPECTED_RESULT]\n{result_data['expected_result_str']}\n[/EXPECTED_RESULT]"
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
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Execute initialization
            if init_query:
                for statement in init_query.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
                conn.commit()
            
            # Execute test query
            cursor.execute(test_query)
            result = cursor.fetchall()
            
            # Get column names
            columns = [description[0] for description in cursor.description] if cursor.description else []
            
            return {
                "success": True,
                "columns": columns,
                "rows": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            try:
                conn.close()
            except:
                pass
            try:
                os.unlink(db_path)
            except:
                pass


def load(app):
    """Load the SQL challenge plugin."""
    from CTFd.plugins.migrations import upgrade
    
    # Upgrade database to include SQL challenge tables
    upgrade()
    
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