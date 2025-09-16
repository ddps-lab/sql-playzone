package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	sqle "github.com/dolthub/go-mysql-server"
	"github.com/dolthub/go-mysql-server/memory"
	"github.com/dolthub/go-mysql-server/sql"
)

type QueryRequest struct {
	InitQuery     string `json:"init_query"`
	SolutionQuery string `json:"solution_query"`
	UserQuery     string `json:"user_query"`
	ClientIP      string `json:"client_ip,omitempty"`
	UserID        string `json:"user_id,omitempty"`
	UserName      string `json:"user_name,omitempty"`
	ChallengeID   string `json:"challenge_id,omitempty"`
}

type QueryResponse struct {
	Success        bool        `json:"success"`
	Match          bool        `json:"match"`
	UserResult     QueryResult `json:"user_result"`
	ExpectedResult QueryResult `json:"expected_result"`
	Error          string      `json:"error,omitempty"`
}

type QueryResult struct {
	Columns  []string   `json:"columns"`
	Rows     [][]string `json:"rows"`
	RowCount int        `json:"row_count"`
}

// Security: List of dangerous SQL functions and keywords to block
var dangerousFunctions = []string{
	// File operations
	"LOAD_FILE",
	"INTO OUTFILE",
	"INTO DUMPFILE",
	"LOAD DATA",
	"LOAD XML",
	"FILE",
	"HANDLER",
	
	// System operations
	"SYSTEM",
	"SHELL",
	"EXEC",
	"EXECUTE",
	"XP_CMDSHELL",
	"SP_OA",
	
	// Time-based attacks
	"BENCHMARK",
	"SLEEP",
	"WAITFOR",
	"DELAY",
	"PG_SLEEP",
	"RANDOMBLOB",
	
	// Lock operations
	"GET_LOCK",
	"RELEASE_LOCK",
	"MASTER_POS_WAIT",
	"IS_FREE_LOCK",
	"IS_USED_LOCK",
	
	// XML operations (can be used for XXE)
	"EXTRACTVALUE",
	"UPDATEXML",
	"XMLTYPE",
	
	// Extension loading
	"LOAD_EXTENSION",
	"CREATE EXTENSION",
	
	// Database specific dangerous functions
	"GENERATE_SERIES",
	"UTL_",
	"DBMS_",
	"SYS.",
	"SYS_",
	
	// Access to sensitive system tables
	"INFORMATION_SCHEMA.PROCESSLIST",
	"PERFORMANCE_SCHEMA",
	"MYSQL.USER",
	"PG_SHADOW",
	"PG_AUTHID",
	
	// Network operations
	"UTL_HTTP",
	"UTL_TCP",
	"OPENROWSET",
	"OPENDATASOURCE",
	"OPENQUERY",
	
	// Other dangerous operations
	"GRANT",
	"REVOKE",
	"CREATE USER",
	"DROP USER",
	"ALTER USER",
	"SET ROLE",
	"SET SESSION AUTHORIZATION",
}

// logSecurityEvent logs security-related events with context
func logSecurityEvent(eventType string, details string, req *QueryRequest) {
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	clientInfo := ""
	if req != nil {
		clientInfo = fmt.Sprintf(" [IP: %s, User: %s, Challenge: %s]", 
			req.ClientIP, req.UserID, req.ChallengeID)
	}
	log.Printf("[%s] SECURITY %s: %s%s", timestamp, eventType, details, clientInfo)
}

// Security: Validate SQL query for dangerous operations
func validateSQLQuery(query string, req *QueryRequest) error {
	upperQuery := strings.ToUpper(query)
	
	// Check for dangerous functions
	for _, dangerous := range dangerousFunctions {
		if strings.Contains(upperQuery, strings.ToUpper(dangerous)) {
			logSecurityEvent("BLOCKED", fmt.Sprintf("Dangerous function: %s", dangerous), req)
			return fmt.Errorf("security violation: dangerous function '%s' is not allowed", dangerous)
		}
	}
	
	// Check for file system operations using regex
	fileOpsPattern := regexp.MustCompile(`(?i)(LOAD_FILE|INTO\s+(OUTFILE|DUMPFILE)|LOAD\s+DATA)`)
	if fileOpsPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "File system operation attempt", req)
		return fmt.Errorf("security violation: file system operations are not allowed")
	}
	
	// Check for system command execution patterns
	systemPattern := regexp.MustCompile(`(?i)(sys_exec|sys_eval|system|shell|exec|execute|xp_cmdshell)`)
	if systemPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "System command execution attempt", req)
		return fmt.Errorf("security violation: system command execution is not allowed")
	}
	
	// Check for SQL injection patterns in comments
	commentPattern := regexp.MustCompile(`(?i)(\/\*.*\*\/|--.*$|#.*$)`)
	if commentPattern.MatchString(query) {
		// Allow simple comments but check for nested dangerous content
		comments := commentPattern.FindAllString(query, -1)
		for _, comment := range comments {
			for _, dangerous := range dangerousFunctions {
				if strings.Contains(strings.ToUpper(comment), strings.ToUpper(dangerous)) {
					logSecurityEvent("BLOCKED", fmt.Sprintf("Dangerous function in comment: %s", dangerous), req)
					return fmt.Errorf("security violation: dangerous content in comments")
				}
			}
		}
	}
	
	// Check for union-based injection with information_schema
	unionPattern := regexp.MustCompile(`(?i)UNION.*SELECT.*(INFORMATION_SCHEMA|MYSQL\.|PERFORMANCE_SCHEMA)`)
	if unionPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "UNION with system tables attempt", req)
		return fmt.Errorf("security violation: accessing system tables via UNION is not allowed")
	}
	
	return nil
}

// cleanupSQLStatement processes SQL statements to ensure compatibility
// Table 생성할 때 Foreign Key 로 constraint 를 생성시 기존의 MySQL 에서는 자동으로 Name 을 생성해 준다.
// 하지만 go-mysql-server 에서는 자동으로 Foreign Key Name 을 생성해 주지 않기 떄문에 수동으로 Name 을 생성해 주어야 한다.
// 예시:
// -- 이름 없는 FK (MySQL 에서는 허용되지만 go-mysql-server 에서는 오류 발생)
// CREATE TABLE orders (
//     id INT PRIMARY KEY,
//     user_id INT,
//     FOREIGN KEY (user_id) REFERENCES users(id)  -- 이름이 없음!
// );

// -- 이름 있는 FK (아래와 같이 명시적 지정 해주어야 함)
// CREATE TABLE orders (
//     id INT PRIMARY KEY,
//     user_id INT,
//     CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
// );
func cleanupSQLStatement(stmt string) string {
	// Generate unique names for unnamed FOREIGN KEY constraints
	// This prevents "duplicate foreign key constraint name" errors
	if strings.Contains(strings.ToUpper(stmt), "FOREIGN KEY") {
		// Simple counter-based approach for unique constraint names
		timestamp := time.Now().UnixNano()
		fkCounter := 0
		
		// Find and replace unnamed FOREIGN KEY constraints
		lines := strings.Split(stmt, "\n")
		for i, line := range lines {
			if strings.Contains(strings.ToUpper(line), "FOREIGN KEY") && 
			   !strings.Contains(strings.ToUpper(line), "CONSTRAINT") {
				// Add a unique constraint name
				fkCounter++
				constraintName := fmt.Sprintf("fk_%d_%d", timestamp, fkCounter)
				lines[i] = strings.Replace(line, "FOREIGN KEY", 
					fmt.Sprintf("CONSTRAINT %s FOREIGN KEY", constraintName), 1)
			}
		}
		stmt = strings.Join(lines, "\n")
	}
	
	return stmt
}

func executeQuery(initQueries []string, query string, req *QueryRequest) (*QueryResult, error) {
	// Security: Validate the user query before execution
	if err := validateSQLQuery(query, req); err != nil {
		return nil, err
	}
	
	dbName := "ctfd_sql_challenge"
	db := memory.NewDatabase(dbName)
	db.EnablePrimaryKeyIndexes()  // Enable primary key indexes
	
	pro := memory.NewDBProvider(db)
	engine := sqle.NewDefault(pro)

	session := memory.NewSession(sql.NewBaseSession(), pro)
	ctx := sql.NewContext(context.Background(), sql.WithSession(session))
	ctx.SetCurrentDatabase(dbName)
	
	// Set session variables for MySQL compatibility
	session.SetSessionVariable(ctx, "autocommit", true)
	session.SetSessionVariable(ctx, "character_set_server", "utf8mb4")
	session.SetSessionVariable(ctx, "collation_server", "utf8mb4_unicode_ci")
	session.SetSessionVariable(ctx, "character_set_database", "utf8mb4")
	session.SetSessionVariable(ctx, "collation_database", "utf8mb4_unicode_ci")

	// Set timeout for query execution
	timeoutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx = sql.NewContext(timeoutCtx, sql.WithSession(session))
	ctx.SetCurrentDatabase(dbName)
	
	// Execute initialization queries
	for _, initQuery := range initQueries {
		if strings.TrimSpace(initQuery) == "" {
			continue
		}

		// Security: Validate init queries as well (with more lenient rules for CREATE/INSERT)
		// We still want to prevent file operations in init queries
		if err := validateSQLQuery(initQuery, req); err != nil {
			// For init queries, we might want to be slightly more permissive
			// but still block file operations
			if strings.Contains(err.Error(), "file") || strings.Contains(err.Error(), "system") {
				return nil, fmt.Errorf("security violation in init query: %v", err)
			}
		}

		// Split by semicolon for multiple statements
		statements := strings.Split(initQuery, ";")
		for _, stmt := range statements {
			stmt = strings.TrimSpace(stmt)
			if stmt == "" {
				continue
			}
			
			// Remove charset/collate clauses that go-mysql-server might not support
			originalStmt := stmt
			stmt = cleanupSQLStatement(stmt)
			
			logMaxLength := 200
			// 일반적인 상황에서는 이제 로깅은 나중에 디버깅용으로 남겨둠.
			// 너무 많은 로그가 발생하여 진짜 로그를 판별하기 어렵게 됨
			// // Log the statement for debugging
			// if strings.Contains(strings.ToUpper(stmt), "CREATE") || strings.Contains(strings.ToUpper(stmt), "INSERT") {
			// 	if len(stmt) > logMaxLength {
			// 		log.Printf("Executing (truncated): %s...", stmt[:logMaxLength])
			// 	} else {
			// 		log.Printf("Executing: %s", stmt)
			// 	}
			// }

			_, iter, err := engine.Query(ctx, stmt)
			if err != nil {
				if len(stmt) > logMaxLength {
					log.Printf("Failed to execute (truncated): %s...", stmt[:logMaxLength])
				} else {
					log.Printf("Failed to execute: %s", stmt)
				}
				if len(originalStmt) > logMaxLength {
					log.Printf("Failed to execute (truncated): %s...", originalStmt[:logMaxLength])
				} else {
					log.Printf("Failed to execute: %s", originalStmt)
				}
				return nil, fmt.Errorf("init query error: %v", err)
			}

			// Consume the iterator
			if iter != nil {
				_, err = sql.RowIterToRows(ctx, iter)
				if err != nil {
					return nil, fmt.Errorf("init query iteration error: %v", err)
				}
			}
		}
	}

	// Execute the main query
	schema, iter, err := engine.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query error: %v", err)
	}

	// Get column names
	var columns []string
	if schema != nil {
		for _, col := range schema {
			columns = append(columns, col.Name)
		}
	}

	// Get rows
	rows, err := sql.RowIterToRows(ctx, iter)
	if err != nil {
		return nil, fmt.Errorf("row iteration error: %v", err)
	}

	// Convert rows to string format
	var stringRows [][]string
	for _, row := range rows {
		var stringRow []string
		for _, val := range row {
			if val == nil {
				stringRow = append(stringRow, "NULL")
			} else {
				stringRow = append(stringRow, fmt.Sprintf("%v", val))
			}
		}
		stringRows = append(stringRows, stringRow)
	}

	return &QueryResult{
		Columns:  columns,
		Rows:     stringRows,
		RowCount: len(stringRows),
	}, nil
}

func handleJudge(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req QueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Log incoming request
	logSecurityEvent("REQUEST", fmt.Sprintf("Query submission for challenge"), &req)
	
	// Prepare init queries
	initQueries := []string{req.InitQuery}

	// Log User Info
	if req.UserID != "" || req.UserName != "" || req.ClientIP != "" || req.ChallengeID != "" {
		log.Printf("Start Query Execution [UserID: %s, UserName: %s, IP: %s, ChallengeID: %s]",
			req.UserID, req.UserName, req.ClientIP, req.ChallengeID)
	} else {
		log.Printf("Start Query Execution [Anonymous User, IP: %s, ChallengeID: %s]",
			req.ClientIP, req.ChallengeID)
	}

	// Execute expected result
	expectedResult, err := executeQuery(initQueries, req.SolutionQuery, &req)
	if err != nil {
		resp := QueryResponse{
			Success: false,
			Error:   fmt.Sprintf("Failed to execute solution query: %v", err),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
		return
	}

	// Execute user query
	userResult, err := executeQuery(initQueries, req.UserQuery, &req)
	if err != nil {
		resp := QueryResponse{
			Success: false,
			Error:   fmt.Sprintf("Failed to execute user query: %v", err),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
		return
	}

	// Compare results
	match := compareResults(expectedResult, userResult)

	resp := QueryResponse{
		Success:        true,
		Match:          match,
		UserResult:     *userResult,
		ExpectedResult: *expectedResult,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func compareResults(expected, actual *QueryResult) bool {
	// Compare row count
	if expected.RowCount != actual.RowCount {
		return false
	}

	// Compare column count (not names, as they might differ)
	if len(expected.Columns) != len(actual.Columns) {
		return false
	}

	// Compare rows (order matters for now)
	if len(expected.Rows) != len(actual.Rows) {
		return false
	}

	for i, expectedRow := range expected.Rows {
		if len(expectedRow) != len(actual.Rows[i]) {
			return false
		}
		for j, expectedVal := range expectedRow {
			if expectedVal != actual.Rows[i][j] {
				return false
			}
		}
	}

	return true
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func setupLogging() {
	// Get log folder from environment variable, default to /var/log/CTFd
	logFolder := os.Getenv("LOG_FOLDER")
	if logFolder == "" {
		logFolder = "/var/log/CTFd"
	}

	// Create log directory if it doesn't exist
	if err := os.MkdirAll(logFolder, 0755); err != nil {
		log.Printf("Warning: Could not create log directory %s: %v", logFolder, err)
		log.Printf("Logging to stdout only")
		return
	}

	// Create or open log file
	logPath := filepath.Join(logFolder, "sql-judge.log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Printf("Warning: Could not open log file %s: %v", logPath, err)
		log.Printf("Logging to stdout only")
		return
	}

	// Set log output to both file and stdout using io.MultiWriter
	multiWriter := io.MultiWriter(os.Stdout, logFile)
	log.SetOutput(multiWriter)
	
	// Set log format with timestamp
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)
	
	log.Printf("SQL Judge Server logging initialized. Log file: %s", logPath)
}

func main() {
	// Setup logging first
	setupLogging()
	
	http.HandleFunc("/judge", handleJudge)
	http.HandleFunc("/health", handleHealth)

	port := "8080"
	log.Printf("SQL Judge Server starting on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatal("Server failed to start:", err)
	}
}
