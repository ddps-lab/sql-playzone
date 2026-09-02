# SQL Challenge Plugin for CTFd

A CTFd plugin that adds SQL challenge type where users submit SQL queries to solve challenges.

## Features

- **SQL Challenge Type**: Create challenges where users must write SQL queries to get the correct result
- **Initialization Queries**: Set up database schema and initial data with CREATE and INSERT statements
- **Solution Query**: Define the correct SQL query that produces the expected result
- **Test Interface**: Test your queries directly in the admin interface before publishing
- **Real MySQL Semantics**: Executes challenge SQL against an isolated MySQL 8.4 database
- **Per-execution Isolation**: Gives each solution and submission execution its own temporary database and restricted MySQL account
- **Custom Query Testing**: Admins can test custom queries against the initialized database

## Installation

The plugin is automatically loaded when CTFd starts. It's located in:
```
CTFd/plugins/sql_challenges/
```

### Running with Docker Compose

```bash
docker-compose up -d
```

This will start:
- CTFd application
- SQL Judge server
- A dedicated MySQL 8.4 instance used only by SQL Judge
- Nginx proxy

Before starting the local Compose stack, create `platform/.env.judge` with a local-only password:

```dotenv
MYSQL_ROOT_PASSWORD=<random local password>
```

The judge MySQL service has no host port. CTFd reaches the Go server through the internal Compose network, while only the Go server can reach the judge database. CTFd waits for the judge `/health` check before it starts, so a freshly booted instance never accepts submissions it cannot grade.

### Manual Server Start

To manually build and run the SQL Judge server:

```bash
cd CTFd/plugins/sql_challenges
MYSQL_HOST=127.0.0.1 \
MYSQL_ROOT_PASSWORD=<local MySQL root password> \
./build.sh run
```

Running the Go server outside Compose requires a separately running MySQL 8.4 instance whose root account accepts the configured TCP connection.

### Tests

Unit tests run in any Go 1.24 environment. The repository integration script starts a disposable MySQL container and removes its containers and volumes on completion:

```bash
scripts/test-sql-judge
```

## Usage

### Creating a SQL Challenge

Read [AUTHORING.md](AUTHORING.md) (Korean) before writing a challenge. It explains what the judge accepts in init SQL, how results are compared, and which words are blocked.

Init scripts exported from a local MySQL can keep their `DROP SCHEMA`, `CREATE SCHEMA` and `USE` statements: the judge maps that schema name onto the execution's temporary database and skips those statements, so `kbo.PLAYER` in init or in a submission resolves to the temporary database. `SET` statements in the init script, such as `SET SQL_MODE='TRADITIONAL'`, stay in effect for the graded statement exactly as they would in one local MySQL session. Leading comment lines, including `-----` separators that MySQL itself rejects, are removed from each statement. Table names are case-insensitive (`lower_case_table_names=1`, the Windows and macOS default), so `Salaries` and `salaries` refer to the same table. This setting is fixed when the MySQL data directory is initialized; an existing `mysql-judge-data` volume must be removed before changing it.

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

- Solution and submission queries receive separate temporary databases and separate restricted MySQL accounts
- Each execution uses two accounts: an init account with full privileges on its temporary database runs the challenge init SQL, and a `SELECT`-only account runs the graded statement, so a submission cannot run DML or DDL, or create events, triggers, or routines
- The MySQL event scheduler is disabled and the `MAX_EXECUTION_TIME` optimizer hint is rejected, so a submission cannot outlive its per-statement time limit
- Student SQL never runs through the MySQL root control connection
- MySQL is isolated on a Docker network that CTFd does not join and does not expose a host port
- Temporary accounts and databases are deleted after every execution; startup cleanup and a five-minute live-set-aware sweep remove leftovers from interrupted cleanup, including sessions whose account was already dropped
- The server collation is `utf8mb4_0900_ai_ci`, the MySQL 8 default, so ordering and comparison match a local MySQL 8 installation
- No persistent data or access to the main CTFd database
- A judge request has an 8-second default budget within CTFd's 10-second client timeout
- Query, request size, result size, row count, and concurrency limits are configurable through `SQL_JUDGE_*` environment variables
- Server runs in a separate process with limited permissions

## File Structure

```
sql_challenges/
├── __init__.py          # Main plugin code
├── README.md            # This file
├── sql_judge_server.go  # Go-based MySQL judge server
├── go.mod               # Go module dependencies
├── go.sum               # Go dependency checksums (auto-generated)
├── Dockerfile           # Docker image for judge server
├── build.sh             # Build script for judge server
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
