package main

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	mysql "github.com/go-sql-driver/mysql"
)

const (
	temporaryDatabasePrefix = "ctfd_tmp_"
	temporaryUserPrefix     = "ct_"
	temporaryCollation      = "utf8mb4_0900_ai_ci" // MySQL 8 default, so results match a local MySQL 8 install
)

var (
	temporaryDatabasePattern = regexp.MustCompile(`^ctfd_tmp_[0-9a-f]{32}$`)
	temporaryUserPattern     = regexp.MustCompile(`^ct_[0-9a-f]{16}$`)
	temporaryPasswordPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
	errResultLimit           = errors.New("query result exceeds configured limit")
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

type Config struct {
	MySQLHost         string
	MySQLPort         string
	MySQLRootPassword string
	ListenAddress     string
	StartupTimeout    time.Duration
	RequestTimeout    time.Duration
	QueryTimeout      time.Duration
	QueueTimeout      time.Duration
	CleanupTimeout    time.Duration
	SweepInterval     time.Duration
	MaxConcurrent     int
	MaxRequestBytes   int64
	MaxResultRows     int
	MaxResultBytes    int64
}

type Server struct {
	config    Config
	controlDB *sql.DB
	slots     chan struct{}
	liveMu    sync.RWMutex
	live      map[string]struct{}
}

// executionResources names the disposable MySQL objects of one execution. The
// init account owns the temporary database so challenge DDL and data loading
// work. The graded statement runs under a separate read-only account, so a
// single submission cannot create events, routines, triggers, or tables, and
// cannot run DML that max_execution_time would not bound.
type executionResources struct {
	database      string
	initUser      string
	initPassword  string
	queryUser     string
	queryPassword string
}

func (r executionResources) users() []string { return []string{r.initUser, r.queryUser} }

func newExecutionResources() (executionResources, error) {
	var r executionResources
	var err error
	if r.database, err = randomName(temporaryDatabasePrefix, 16); err != nil {
		return r, fmt.Errorf("generate temporary database name: %w", err)
	}
	if r.initUser, err = randomName(temporaryUserPrefix, 8); err != nil {
		return r, fmt.Errorf("generate temporary user name: %w", err)
	}
	if r.initPassword, err = randomHex(32); err != nil {
		return r, fmt.Errorf("generate temporary user password: %w", err)
	}
	if r.queryUser, err = randomName(temporaryUserPrefix, 8); err != nil {
		return r, fmt.Errorf("generate temporary user name: %w", err)
	}
	if r.queryPassword, err = randomHex(32); err != nil {
		return r, fmt.Errorf("generate temporary user password: %w", err)
	}
	return r, nil
}

// MySQL privileges are the primary isolation boundary. This list preserves
// the existing defense-in-depth behavior and its compatibility characteristics.
var dangerousFunctions = []string{
	"LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE", "LOAD DATA", "LOAD XML", "FILE", "HANDLER",
	"SYSTEM", "SHELL", "EXEC", "EXECUTE", "XP_CMDSHELL", "SP_OA",
	"BENCHMARK", "SLEEP", "WAITFOR", "DELAY", "PG_SLEEP", "RANDOMBLOB",
	"GET_LOCK", "RELEASE_LOCK", "MASTER_POS_WAIT", "IS_FREE_LOCK", "IS_USED_LOCK",
	"EXTRACTVALUE", "UPDATEXML", "XMLTYPE", "LOAD_EXTENSION", "CREATE EXTENSION",
	"GENERATE_SERIES", "UTL_", "DBMS_", "SYS.", "SYS_",
	"INFORMATION_SCHEMA.PROCESSLIST", "PERFORMANCE_SCHEMA", "MYSQL.USER", "PG_SHADOW", "PG_AUTHID",
	"UTL_HTTP", "UTL_TCP", "OPENROWSET", "OPENDATASOURCE", "OPENQUERY",
	"GRANT", "REVOKE", "CREATE USER", "DROP USER", "ALTER USER", "SET ROLE", "SET SESSION AUTHORIZATION",
	// The optimizer hint would override the SET SESSION max_execution_time applied to every graded statement.
	"MAX_EXECUTION_TIME",
}

func defaultConfig() Config {
	return Config{
		MySQLHost:       "mysql-judge",
		MySQLPort:       "3306",
		ListenAddress:   ":8080",
		StartupTimeout:  60 * time.Second,
		RequestTimeout:  8 * time.Second,
		QueryTimeout:    2500 * time.Millisecond,
		QueueTimeout:    2 * time.Second,
		CleanupTimeout:  time.Second,
		SweepInterval:   5 * time.Minute,
		MaxConcurrent:   16,
		MaxRequestBytes: 1 << 20,
		MaxResultRows:   1000,
		MaxResultBytes:  4 << 20,
	}
}

func loadConfig(getenv func(string) string) (Config, error) {
	cfg := defaultConfig()
	if value := getenv("MYSQL_HOST"); value != "" {
		cfg.MySQLHost = value
	}
	if value := getenv("MYSQL_PORT"); value != "" {
		cfg.MySQLPort = value
	}
	if value := getenv("SQL_JUDGE_LISTEN_ADDRESS"); value != "" {
		cfg.ListenAddress = value
	}
	cfg.MySQLRootPassword = getenv("MYSQL_ROOT_PASSWORD")
	if cfg.MySQLRootPassword == "" {
		return Config{}, errors.New("MYSQL_ROOT_PASSWORD must be set")
	}

	var err error
	if cfg.StartupTimeout, err = durationSetting(getenv, "MYSQL_STARTUP_TIMEOUT", cfg.StartupTimeout); err != nil {
		return Config{}, err
	}
	if cfg.RequestTimeout, err = durationSetting(getenv, "SQL_JUDGE_REQUEST_TIMEOUT", cfg.RequestTimeout); err != nil {
		return Config{}, err
	}
	if cfg.QueryTimeout, err = durationSetting(getenv, "SQL_JUDGE_QUERY_TIMEOUT", cfg.QueryTimeout); err != nil {
		return Config{}, err
	}
	if cfg.QueueTimeout, err = durationSetting(getenv, "SQL_JUDGE_QUEUE_TIMEOUT", cfg.QueueTimeout); err != nil {
		return Config{}, err
	}
	if cfg.CleanupTimeout, err = durationSetting(getenv, "SQL_JUDGE_CLEANUP_TIMEOUT", cfg.CleanupTimeout); err != nil {
		return Config{}, err
	}
	if cfg.SweepInterval, err = durationSetting(getenv, "SQL_JUDGE_SWEEP_INTERVAL", cfg.SweepInterval); err != nil {
		return Config{}, err
	}
	if cfg.MaxConcurrent, err = intSetting(getenv, "SQL_JUDGE_MAX_CONCURRENT", cfg.MaxConcurrent); err != nil {
		return Config{}, err
	}
	if cfg.MaxRequestBytes, err = int64Setting(getenv, "SQL_JUDGE_MAX_REQUEST_BYTES", cfg.MaxRequestBytes); err != nil {
		return Config{}, err
	}
	if cfg.MaxResultRows, err = intSetting(getenv, "SQL_JUDGE_MAX_RESULT_ROWS", cfg.MaxResultRows); err != nil {
		return Config{}, err
	}
	if cfg.MaxResultBytes, err = int64Setting(getenv, "SQL_JUDGE_MAX_RESULT_BYTES", cfg.MaxResultBytes); err != nil {
		return Config{}, err
	}
	if cfg.QueryTimeout >= cfg.RequestTimeout {
		return Config{}, errors.New("SQL_JUDGE_QUERY_TIMEOUT must be shorter than SQL_JUDGE_REQUEST_TIMEOUT")
	}
	if 2*(cfg.QueryTimeout+cfg.CleanupTimeout) > cfg.RequestTimeout {
		return Config{}, errors.New("two query and cleanup budgets must fit within SQL_JUDGE_REQUEST_TIMEOUT")
	}
	return cfg, nil
}

func durationSetting(getenv func(string) string, name string, fallback time.Duration) (time.Duration, error) {
	value := getenv(name)
	if value == "" {
		return fallback, nil
	}
	parsed, err := time.ParseDuration(value)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration", name)
	}
	return parsed, nil
}

func intSetting(getenv func(string) string, name string, fallback int) (int, error) {
	value := getenv(name)
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return parsed, nil
}

func int64Setting(getenv func(string) string, name string, fallback int64) (int64, error) {
	value := getenv(name)
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return parsed, nil
}

func newServer(ctx context.Context, cfg Config) (*Server, error) {
	controlConfig := mysql.NewConfig()
	controlConfig.User = "root"
	controlConfig.Passwd = cfg.MySQLRootPassword
	controlConfig.Net = "tcp"
	controlConfig.Addr = net.JoinHostPort(cfg.MySQLHost, cfg.MySQLPort)
	controlConfig.Timeout = 5 * time.Second
	controlConfig.ReadTimeout = 5 * time.Second
	controlConfig.WriteTimeout = 5 * time.Second
	controlConfig.MultiStatements = false
	controlConfig.ParseTime = false

	controlDB, err := sql.Open("mysql", controlConfig.FormatDSN())
	if err != nil {
		return nil, fmt.Errorf("open MySQL control connection: %w", err)
	}
	controlDB.SetMaxOpenConns(cfg.MaxConcurrent)
	controlDB.SetMaxIdleConns(4)
	controlDB.SetConnMaxLifetime(15 * time.Minute)
	controlDB.SetConnMaxIdleTime(5 * time.Minute)

	server := &Server{
		config: cfg, controlDB: controlDB,
		slots: make(chan struct{}, cfg.MaxConcurrent), live: make(map[string]struct{}),
	}
	if err := server.waitForMySQL(ctx); err != nil {
		controlDB.Close()
		return nil, err
	}
	if err := server.cleanupStaleResources(ctx); err != nil {
		log.Printf("Warning: Initial stale SQL Judge resource cleanup was incomplete: %v", err)
	}
	return server, nil
}

func (s *Server) waitForMySQL(parent context.Context) error {
	ctx, cancel := context.WithTimeout(parent, s.config.StartupTimeout)
	defer cancel()
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		pingCtx, pingCancel := context.WithTimeout(ctx, 3*time.Second)
		err := s.controlDB.PingContext(pingCtx)
		pingCancel()
		if err == nil {
			return nil
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("wait for MySQL: %w", ctx.Err())
		case <-ticker.C:
		}
	}
}

func (s *Server) cleanupStaleResources(parent context.Context) error {
	ctx, cancel := context.WithTimeout(parent, 10*time.Second)
	defer cancel()

	databaseRows, err := s.controlDB.QueryContext(ctx, "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA")
	if err != nil {
		return fmt.Errorf("list stale databases: %w", err)
	}
	var databases []string
	for databaseRows.Next() {
		var name string
		if err := databaseRows.Scan(&name); err != nil {
			databaseRows.Close()
			return fmt.Errorf("scan stale database: %w", err)
		}
		if temporaryDatabasePattern.MatchString(name) {
			databases = append(databases, name)
		}
	}
	if err := databaseRows.Err(); err != nil {
		databaseRows.Close()
		return fmt.Errorf("iterate stale databases: %w", err)
	}
	databaseRows.Close()

	userRows, err := s.controlDB.QueryContext(ctx, "SELECT User FROM mysql.user")
	if err != nil {
		return fmt.Errorf("list stale users: %w", err)
	}
	var users []string
	for userRows.Next() {
		var name string
		if err := userRows.Scan(&name); err != nil {
			userRows.Close()
			return fmt.Errorf("scan stale user: %w", err)
		}
		if temporaryUserPattern.MatchString(name) {
			users = append(users, name)
		}
	}
	if err := userRows.Err(); err != nil {
		userRows.Close()
		return fmt.Errorf("iterate stale users: %w", err)
	}
	userRows.Close()

	// Sessions are matched by account name pattern rather than by mysql.user so
	// that a thread whose account was already dropped is still stopped.
	type staleSession struct {
		id   uint64
		user string
	}
	sessionRows, err := s.controlDB.QueryContext(ctx, "SELECT ID, USER FROM INFORMATION_SCHEMA.PROCESSLIST WHERE USER LIKE 'ct\\_%'")
	if err != nil {
		return fmt.Errorf("list stale sessions: %w", err)
	}
	var sessions []staleSession
	for sessionRows.Next() {
		var session staleSession
		if err := sessionRows.Scan(&session.id, &session.user); err != nil {
			sessionRows.Close()
			return fmt.Errorf("scan stale session: %w", err)
		}
		if temporaryUserPattern.MatchString(session.user) {
			sessions = append(sessions, session)
		}
	}
	if err := sessionRows.Err(); err != nil {
		sessionRows.Close()
		return fmt.Errorf("iterate stale sessions: %w", err)
	}
	sessionRows.Close()

	var cleanupErrors []error
	stoppedSessions := 0
	for _, session := range sessions {
		if s.resourceIsLive(session.user) {
			continue
		}
		if _, err := s.controlDB.ExecContext(ctx, fmt.Sprintf("KILL CONNECTION %d", session.id)); err != nil && !strings.Contains(err.Error(), "Unknown thread id") {
			cleanupErrors = append(cleanupErrors, fmt.Errorf("stop stale session %d of %s: %w", session.id, session.user, err))
			continue
		}
		stoppedSessions++
	}
	droppedDatabases := 0
	for _, name := range databases {
		if s.resourceIsLive(name) {
			continue
		}
		if _, err := s.controlDB.ExecContext(ctx, "DROP DATABASE IF EXISTS "+quoteIdentifier(name)); err != nil {
			cleanupErrors = append(cleanupErrors, fmt.Errorf("drop stale database %s: %w", name, err))
			continue
		}
		droppedDatabases++
	}
	droppedUsers := 0
	for _, name := range users {
		if s.resourceIsLive(name) {
			continue
		}
		if _, err := s.controlDB.ExecContext(ctx, "DROP USER IF EXISTS "+quoteAccount(name)); err != nil {
			cleanupErrors = append(cleanupErrors, fmt.Errorf("drop stale user %s: %w", name, err))
			continue
		}
		droppedUsers++
	}
	if droppedDatabases > 0 || droppedUsers > 0 || stoppedSessions > 0 {
		log.Printf("Removed %d stale judge databases and %d stale judge users, stopped %d stale sessions", droppedDatabases, droppedUsers, stoppedSessions)
	}
	return errors.Join(cleanupErrors...)
}

func (s *Server) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/judge", s.handleJudge)
	mux.HandleFunc("/health", s.handleHealth)
	return mux
}

func (s *Server) handleJudge(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, s.config.MaxRequestBytes)
	decoder := json.NewDecoder(r.Body)
	var req QueryRequest
	if err := decoder.Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), s.config.RequestTimeout)
	defer cancel()
	queueTimer := time.NewTimer(s.config.QueueTimeout)
	defer queueTimer.Stop()
	select {
	case s.slots <- struct{}{}:
		defer func() { <-s.slots }()
	case <-queueTimer.C:
		writeJSON(w, QueryResponse{Success: false, Error: "SQL judge is busy; please retry"})
		return
	case <-ctx.Done():
		writeJSON(w, QueryResponse{Success: false, Error: "SQL judge request timed out while waiting"})
		return
	}

	logSecurityEvent("REQUEST", "Query submission for challenge", &req)
	log.Printf("Start Query Execution [UserID: %s, UserName: %s, IP: %s, ChallengeID: %s]",
		req.UserID, req.UserName, req.ClientIP, req.ChallengeID)
	initQueries := []string{req.InitQuery}
	expectedResult, err := s.executeQuery(ctx, initQueries, req.SolutionQuery, &req)
	if err != nil {
		writeJSON(w, QueryResponse{Success: false, Error: fmt.Sprintf("Failed to execute solution query: %v", err)})
		return
	}
	userResult, err := s.executeQuery(ctx, initQueries, req.UserQuery, &req)
	if err != nil {
		writeJSON(w, QueryResponse{Success: false, Error: fmt.Sprintf("Failed to execute user query: %v", err)})
		return
	}
	writeJSON(w, QueryResponse{Success: true, Match: compareResults(expectedResult, userResult), UserResult: *userResult, ExpectedResult: *expectedResult})
}

func (s *Server) executeQuery(parent context.Context, initQueries []string, query string, req *QueryRequest) (*QueryResult, error) {
	if err := validateSQLQuery(query, req); err != nil {
		return nil, err
	}
	resources, err := newExecutionResources()
	if err != nil {
		return nil, err
	}

	executionCtx, cancel := context.WithTimeout(parent, s.config.QueryTimeout)
	defer cancel()
	s.markExecutionLive(resources)
	// Cleanup is idempotent, so registering it before creation also covers a
	// CREATE that the server applied after the client side was cancelled.
	defer func() {
		s.cleanupExecution(resources)
		s.unmarkExecutionLive(resources)
	}()
	if err := s.createExecutionResources(executionCtx, resources); err != nil {
		return nil, err
	}
	if err := s.runInitStatements(executionCtx, resources, initQueries, req); err != nil {
		return nil, err
	}
	return s.runGradedQuery(executionCtx, resources, query)
}

func (s *Server) openRunner(user, password, database string) (*sql.DB, error) {
	runnerConfig := mysql.NewConfig()
	runnerConfig.User = user
	runnerConfig.Passwd = password
	runnerConfig.Net = "tcp"
	runnerConfig.Addr = net.JoinHostPort(s.config.MySQLHost, s.config.MySQLPort)
	runnerConfig.DBName = database
	runnerConfig.Collation = temporaryCollation
	runnerConfig.Timeout = s.config.QueryTimeout
	runnerConfig.ReadTimeout = s.config.QueryTimeout
	runnerConfig.WriteTimeout = s.config.QueryTimeout
	runnerConfig.MultiStatements = false
	runnerConfig.ParseTime = false

	runnerDB, err := sql.Open("mysql", runnerConfig.FormatDSN())
	if err != nil {
		return nil, fmt.Errorf("open isolated MySQL connection: %w", err)
	}
	runnerDB.SetMaxOpenConns(1)
	runnerDB.SetMaxIdleConns(1)
	return runnerDB, nil
}

func (s *Server) runInitStatements(ctx context.Context, r executionResources, initQueries []string, req *QueryRequest) error {
	var statements []string
	for _, initQuery := range initQueries {
		if strings.TrimSpace(initQuery) == "" {
			continue
		}
		if err := validateSQLQuery(initQuery, req); err != nil {
			if strings.Contains(err.Error(), "file") || strings.Contains(err.Error(), "system") {
				return fmt.Errorf("security violation in init query: %w", err)
			}
		}
		for _, statement := range strings.Split(initQuery, ";") {
			if statement = strings.TrimSpace(statement); statement != "" {
				statements = append(statements, statement)
			}
		}
	}
	if len(statements) == 0 {
		return nil
	}

	initDB, err := s.openRunner(r.initUser, r.initPassword, r.database)
	if err != nil {
		return err
	}
	defer initDB.Close()
	for _, statement := range statements {
		if _, err := initDB.ExecContext(ctx, statement); err != nil {
			return fmt.Errorf("init query error: %w", err)
		}
	}
	return nil
}

func (s *Server) runGradedQuery(ctx context.Context, r executionResources, query string) (*QueryResult, error) {
	queryDB, err := s.openRunner(r.queryUser, r.queryPassword, r.database)
	if err != nil {
		return nil, err
	}
	defer queryDB.Close()
	// Pin one connection so the session limit below applies to the graded statement.
	conn, err := queryDB.Conn(ctx)
	if err != nil {
		return nil, fmt.Errorf("connect isolated MySQL user: %w", err)
	}
	defer conn.Close()

	maxExecutionMilliseconds := s.config.QueryTimeout.Milliseconds()
	if deadline, ok := ctx.Deadline(); ok {
		if remaining := time.Until(deadline).Milliseconds(); remaining < maxExecutionMilliseconds {
			maxExecutionMilliseconds = remaining
		}
	}
	if maxExecutionMilliseconds < 1 {
		return nil, context.DeadlineExceeded
	}
	if _, err := conn.ExecContext(ctx, fmt.Sprintf("SET SESSION max_execution_time = %d", maxExecutionMilliseconds)); err != nil {
		return nil, fmt.Errorf("set query execution limit: %w", err)
	}

	rows, err := conn.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query error: %w", err)
	}
	defer rows.Close()
	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("read result columns: %w", err)
	}
	result := &QueryResult{Columns: columns, Rows: make([][]string, 0)}
	var resultBytes int64
	for rows.Next() {
		if len(result.Rows) >= s.config.MaxResultRows {
			return nil, fmt.Errorf("%w: more than %d rows", errResultLimit, s.config.MaxResultRows)
		}
		rawValues := make([]sql.RawBytes, len(columns))
		destinations := make([]any, len(columns))
		for index := range rawValues {
			destinations[index] = &rawValues[index]
		}
		if err := rows.Scan(destinations...); err != nil {
			return nil, fmt.Errorf("scan result row: %w", err)
		}
		stringRow := make([]string, len(columns))
		for index, value := range rawValues {
			if value == nil {
				stringRow[index] = "NULL"
				resultBytes += 4
			} else {
				stringRow[index] = string(value)
				resultBytes += int64(len(value))
			}
			if resultBytes > s.config.MaxResultBytes {
				return nil, fmt.Errorf("%w: more than %d bytes", errResultLimit, s.config.MaxResultBytes)
			}
		}
		result.Rows = append(result.Rows, stringRow)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate result rows: %w", err)
	}
	result.RowCount = len(result.Rows)
	return result, nil
}

func (s *Server) createExecutionResources(ctx context.Context, r executionResources) error {
	if !temporaryDatabasePattern.MatchString(r.database) || r.initUser == r.queryUser {
		return errors.New("invalid temporary resource")
	}
	for _, user := range r.users() {
		if !temporaryUserPattern.MatchString(user) {
			return errors.New("invalid temporary resource")
		}
	}
	for _, password := range []string{r.initPassword, r.queryPassword} {
		if !temporaryPasswordPattern.MatchString(password) {
			return errors.New("invalid temporary resource")
		}
	}
	steps := []struct{ label, statement string }{
		{"create temporary database", "CREATE DATABASE " + quoteIdentifier(r.database) + " CHARACTER SET utf8mb4 COLLATE " + temporaryCollation},
		{"create init user", "CREATE USER " + quoteAccount(r.initUser) + " IDENTIFIED BY '" + r.initPassword + "' WITH MAX_USER_CONNECTIONS 2"},
		{"grant init privileges", "GRANT ALL PRIVILEGES ON " + quoteIdentifier(r.database) + ".* TO " + quoteAccount(r.initUser)},
		{"create query user", "CREATE USER " + quoteAccount(r.queryUser) + " IDENTIFIED BY '" + r.queryPassword + "' WITH MAX_USER_CONNECTIONS 2"},
		{"grant read-only query privileges", "GRANT SELECT, SHOW VIEW ON " + quoteIdentifier(r.database) + ".* TO " + quoteAccount(r.queryUser)},
	}
	for _, step := range steps {
		if _, err := s.controlDB.ExecContext(ctx, step.statement); err != nil {
			return fmt.Errorf("%s: %w", step.label, err)
		}
	}
	return nil
}

func (s *Server) markExecutionLive(r executionResources) {
	s.liveMu.Lock()
	defer s.liveMu.Unlock()
	s.live[r.database] = struct{}{}
	for _, user := range r.users() {
		s.live[user] = struct{}{}
	}
}

func (s *Server) unmarkExecutionLive(r executionResources) {
	s.liveMu.Lock()
	defer s.liveMu.Unlock()
	delete(s.live, r.database)
	for _, user := range r.users() {
		delete(s.live, user)
	}
}

func (s *Server) resourceIsLive(name string) bool {
	s.liveMu.RLock()
	defer s.liveMu.RUnlock()
	_, ok := s.live[name]
	return ok
}

// The runtime topology has one judge process and one dedicated MySQL per EC2
// instance. The live set prevents the periodic sweeper from touching active
// executions owned by that process.
func (s *Server) runResourceSweeper(ctx context.Context) {
	ticker := time.NewTicker(s.config.SweepInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := s.cleanupStaleResources(ctx); err != nil {
				log.Printf("Failed to sweep stale SQL Judge resources: %v", err)
			}
		}
	}
}

func (s *Server) cleanupExecution(r executionResources) {
	ctx, cancel := context.WithTimeout(context.Background(), s.config.CleanupTimeout)
	defer cancel()
	for _, user := range r.users() {
		if err := s.killUserSessions(ctx, user); err != nil {
			log.Printf("Failed to stop temporary user %s sessions: %v", user, err)
		}
	}
	if temporaryDatabasePattern.MatchString(r.database) {
		if _, err := s.controlDB.ExecContext(ctx, "DROP DATABASE IF EXISTS "+quoteIdentifier(r.database)); err != nil {
			log.Printf("Failed to drop temporary database %s: %v", r.database, err)
		}
	}
	for _, user := range r.users() {
		if !temporaryUserPattern.MatchString(user) {
			continue
		}
		if _, err := s.controlDB.ExecContext(ctx, "DROP USER IF EXISTS "+quoteAccount(user)); err != nil {
			log.Printf("Failed to drop temporary user %s: %v", user, err)
		}
	}
}

func (s *Server) killUserSessions(ctx context.Context, userName string) error {
	if !temporaryUserPattern.MatchString(userName) {
		return errors.New("invalid temporary user name")
	}
	rows, err := s.controlDB.QueryContext(ctx, "SELECT ID FROM INFORMATION_SCHEMA.PROCESSLIST WHERE USER = ?", userName)
	if err != nil {
		return err
	}
	var connectionIDs []uint64
	for rows.Next() {
		var id uint64
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return err
		}
		connectionIDs = append(connectionIDs, id)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return err
	}
	rows.Close()
	for _, id := range connectionIDs {
		if _, err := s.controlDB.ExecContext(ctx, fmt.Sprintf("KILL CONNECTION %d", id)); err != nil && !strings.Contains(err.Error(), "Unknown thread id") {
			return err
		}
	}
	return nil
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.controlDB.PingContext(ctx); err != nil {
		http.Error(w, "MySQL ping failed", http.StatusServiceUnavailable)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("OK"))
}

func compareResults(expected, actual *QueryResult) bool {
	if expected.RowCount != actual.RowCount || len(expected.Columns) != len(actual.Columns) || len(expected.Rows) != len(actual.Rows) {
		return false
	}
	for rowIndex, expectedRow := range expected.Rows {
		if len(expectedRow) != len(actual.Rows[rowIndex]) {
			return false
		}
		for columnIndex, expectedValue := range expectedRow {
			if expectedValue != actual.Rows[rowIndex][columnIndex] {
				return false
			}
		}
	}
	return true
}

func validateSQLQuery(query string, req *QueryRequest) error {
	upperQuery := strings.ToUpper(query)
	for _, dangerous := range dangerousFunctions {
		if strings.Contains(upperQuery, strings.ToUpper(dangerous)) {
			logSecurityEvent("BLOCKED", fmt.Sprintf("Dangerous function: %s", dangerous), req)
			return fmt.Errorf("security violation: dangerous function '%s' is not allowed", dangerous)
		}
	}
	fileOpsPattern := regexp.MustCompile(`(?i)(LOAD_FILE|INTO\s+(OUTFILE|DUMPFILE)|LOAD\s+DATA)`)
	if fileOpsPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "File system operation attempt", req)
		return errors.New("security violation: file system operations are not allowed")
	}
	systemPattern := regexp.MustCompile(`(?i)(sys_exec|sys_eval|system|shell|exec|execute|xp_cmdshell)`)
	if systemPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "System command execution attempt", req)
		return errors.New("security violation: system command execution is not allowed")
	}
	commentPattern := regexp.MustCompile(`(?i)(/\*.*\*/|--.*$|#.*$)`)
	if commentPattern.MatchString(query) {
		for _, comment := range commentPattern.FindAllString(query, -1) {
			for _, dangerous := range dangerousFunctions {
				if strings.Contains(strings.ToUpper(comment), strings.ToUpper(dangerous)) {
					logSecurityEvent("BLOCKED", fmt.Sprintf("Dangerous function in comment: %s", dangerous), req)
					return errors.New("security violation: dangerous content in comments")
				}
			}
		}
	}
	unionPattern := regexp.MustCompile(`(?i)UNION.*SELECT.*(INFORMATION_SCHEMA|MYSQL\.|PERFORMANCE_SCHEMA)`)
	if unionPattern.MatchString(query) {
		logSecurityEvent("BLOCKED", "UNION with system tables attempt", req)
		return errors.New("security violation: accessing system tables via UNION is not allowed")
	}
	return nil
}

func randomName(prefix string, byteCount int) (string, error) {
	random, err := randomHex(byteCount)
	if err != nil {
		return "", err
	}
	return prefix + random, nil
}

func randomHex(byteCount int) (string, error) {
	buffer := make([]byte, byteCount)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}

func quoteIdentifier(name string) string  { return "`" + name + "`" }
func quoteAccount(userName string) string { return "'" + userName + "'@'%'" }

func writeJSON(w http.ResponseWriter, response QueryResponse) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Failed to encode judge response: %v", err)
	}
}

func logSecurityEvent(eventType, details string, req *QueryRequest) {
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	clientInfo := ""
	if req != nil {
		clientInfo = fmt.Sprintf(" [IP: %s, User: %s, Challenge: %s]", req.ClientIP, req.UserID, req.ChallengeID)
	}
	log.Printf("[%s] SECURITY %s: %s%s", timestamp, eventType, details, clientInfo)
}

func setupLogging() {
	logFolder := os.Getenv("LOG_FOLDER")
	if logFolder == "" {
		logFolder = "/var/log/CTFd"
	}
	if err := os.MkdirAll(logFolder, 0o755); err != nil {
		log.Printf("Warning: Could not create log directory %s: %v", logFolder, err)
		return
	}
	logPath := filepath.Join(logFolder, "sql-judge.log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		log.Printf("Warning: Could not open log file %s: %v", logPath, err)
		return
	}
	log.SetOutput(io.MultiWriter(os.Stdout, logFile))
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)
	log.Printf("SQL Judge Server logging initialized. Log file: %s", logPath)
}

func main() {
	setupLogging()
	cfg, err := loadConfig(os.Getenv)
	if err != nil {
		log.Fatalf("Invalid SQL Judge configuration: %v", err)
	}
	server, err := newServer(context.Background(), cfg)
	if err != nil {
		log.Fatalf("Initialize SQL Judge: %v", err)
	}
	defer server.controlDB.Close()
	go server.runResourceSweeper(context.Background())

	httpServer := &http.Server{
		Addr: cfg.ListenAddress, Handler: server.routes(),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second,
		WriteTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second,
	}
	log.Printf("SQL Judge Server starting on %s", cfg.ListenAddress)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal("Server failed to start: ", err)
	}
}
