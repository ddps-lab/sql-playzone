# SQL Challenge Plugin for CTFd

A CTFd plugin that adds SQL challenge type where users submit SQL queries to solve challenges.

## Features

- **SQL Challenge Type**: Create challenges where users must write SQL queries to get the correct result
- **Initialization Queries**: Set up database schema and initial data with CREATE and INSERT statements
- **Solution Query**: Define the correct SQL query that produces the expected result
- **Test Interface**: Test your queries directly in the admin interface before publishing
- **Secure Execution**: SQL queries run in isolated temporary SQLite databases
- **Custom Query Testing**: Admins can test custom queries against the initialized database

## Installation

The plugin is automatically loaded when CTFd starts. It's located in:
```
CTFd/plugins/sql_challenges/
```

## Usage

### Creating a SQL Challenge

1. Go to Admin Panel → Challenges → Create Challenge
2. Select "sql" as the challenge type
3. Fill in the challenge details:
   - **Name**: Challenge title
   - **Category**: Challenge category (e.g., "SQL", "Database")
   - **Value**: Points awarded for solving
   - **Description**: Challenge description (supports Markdown)
   - **Initialization Query**: SQL statements to set up the database
   - **Solution Query**: The correct SQL query that solves the challenge

### Example Challenge

**Initialization Query:**
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER,
    city TEXT
);

INSERT INTO users VALUES (1, 'Alice', 25, 'New York');
INSERT INTO users VALUES (2, 'Bob', 30, 'Los Angeles');
INSERT INTO users VALUES (3, 'Charlie', 28, 'Chicago');
INSERT INTO users VALUES (4, 'Diana', 35, 'New York');
```

**Solution Query:**
```sql
SELECT name FROM users WHERE age > 25 AND city = 'New York';
```

**Challenge Description:**
Find all users older than 25 who live in New York. Return only their names.

### Testing Queries

In the admin interface:
1. Click "Test SQL Queries" to test your solution query
2. Click "Test Custom Query" to test any query against the initialized database
3. Results are displayed in a table format

### For Participants

Participants will:
1. See the database schema (initialization query)
2. Write their SQL query in the submission box
3. Submit to check if their query produces the same result as the solution

## Security

- Each query execution happens in an isolated temporary SQLite database
- Databases are created and destroyed for each test/submission
- No persistent data or access to the main CTFd database
- File system access is restricted to temporary files only

## File Structure

```
sql_challenges/
├── __init__.py          # Main plugin code
├── README.md            # This file
└── assets/
    ├── create.html      # Challenge creation template
    ├── create.js        # Creation page JavaScript
    ├── update.html      # Challenge update template
    ├── update.js        # Update page JavaScript
    ├── view.html        # Challenge view template (for users)
    └── view.js          # View page JavaScript
```

## API Endpoints

- `POST /api/v1/challenges/test-sql`: Test SQL queries (admin only)
  - Request: `{"init_query": "...", "test_query": "..."}`
  - Response: `{"success": true, "columns": [...], "rows": [...]}`

## Database Model

The plugin extends the base `Challenges` model with:
- `init_query`: Text field for initialization SQL
- `solution_query`: Text field for the correct solution

## License

This plugin is part of CTFd and follows the same license.