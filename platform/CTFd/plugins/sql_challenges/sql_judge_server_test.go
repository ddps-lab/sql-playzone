package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestCompareResultsPreservesCurrentContract(t *testing.T) {
	expected := &QueryResult{
		Columns:  []string{"expected_alias"},
		Rows:     [][]string{{"1"}, {"NULL"}},
		RowCount: 2,
	}

	tests := []struct {
		name   string
		actual *QueryResult
		match  bool
	}{
		{
			name:   "column names are ignored",
			actual: &QueryResult{Columns: []string{"different_alias"}, Rows: [][]string{{"1"}, {"NULL"}}, RowCount: 2},
			match:  true,
		},
		{
			name:   "row order matters",
			actual: &QueryResult{Columns: []string{"value"}, Rows: [][]string{{"NULL"}, {"1"}}, RowCount: 2},
			match:  false,
		},
		{
			name:   "row count matters",
			actual: &QueryResult{Columns: []string{"value"}, Rows: [][]string{{"1"}}, RowCount: 1},
			match:  false,
		},
		{
			name:   "column count matters",
			actual: &QueryResult{Columns: []string{"a", "b"}, Rows: [][]string{{"1", "x"}, {"NULL", "y"}}, RowCount: 2},
			match:  false,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := compareResults(expected, test.actual); got != test.match {
				t.Fatalf("compareResults() = %v, want %v", got, test.match)
			}
		})
	}
}

func TestHandleJudgeRejectsOversizedAndBusyRequestsBeforeDatabaseWork(t *testing.T) {
	cfg := defaultConfig()
	cfg.MaxRequestBytes = 64
	server := &Server{config: cfg, slots: make(chan struct{}, 1), live: make(map[string]struct{})}

	oversized := httptest.NewRecorder()
	server.routes().ServeHTTP(oversized, httptest.NewRequest(
		http.MethodPost,
		"/judge",
		strings.NewReader(`{"user_query":"`+strings.Repeat("x", 128)+`"}`),
	))
	if oversized.Code != http.StatusBadRequest {
		t.Fatalf("oversized request status = %d, want %d", oversized.Code, http.StatusBadRequest)
	}

	server.config.MaxRequestBytes = 1 << 20
	server.config.QueueTimeout = time.Millisecond
	server.slots <- struct{}{}
	defer func() { <-server.slots }()
	body, _ := json.Marshal(QueryRequest{SolutionQuery: "SELECT 1", UserQuery: "SELECT 1"})
	busy := httptest.NewRecorder()
	server.routes().ServeHTTP(busy, httptest.NewRequest(http.MethodPost, "/judge", bytes.NewReader(body)))
	var response QueryResponse
	if err := json.Unmarshal(busy.Body.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	if response.Success || !strings.Contains(response.Error, "busy") {
		t.Fatalf("unexpected busy response: %+v", response)
	}
}

func TestValidateSQLQueryPreservesDangerousQueryBlocks(t *testing.T) {
	for _, query := range []string{
		"SELECT SLEEP(10)",
		"SELECT LOAD_FILE('/etc/passwd')",
		"GRANT ALL ON *.* TO attacker",
		"SELECT * FROM mysql.user",
		"SELECT /*+ MAX_EXECUTION_TIME(100000) */ COUNT(*) FROM students",
	} {
		if err := validateSQLQuery(query, nil); err == nil {
			t.Fatalf("validateSQLQuery(%q) unexpectedly succeeded", query)
		}
	}
	if err := validateSQLQuery("SELECT id, name FROM students ORDER BY id", nil); err != nil {
		t.Fatalf("safe query rejected: %v", err)
	}
}

func TestLoadConfigDefaultsAndOverrides(t *testing.T) {
	values := map[string]string{"MYSQL_ROOT_PASSWORD": "root-secret"}
	getenv := func(name string) string { return values[name] }
	cfg, err := loadConfig(getenv)
	if err != nil {
		t.Fatalf("loadConfig() error = %v", err)
	}
	if cfg.RequestTimeout != 8*time.Second || cfg.QueryTimeout != 2500*time.Millisecond {
		t.Fatalf("unexpected timeout defaults: request=%s query=%s", cfg.RequestTimeout, cfg.QueryTimeout)
	}
	if cfg.MaxConcurrent != 16 || cfg.MaxResultRows != 1000 || cfg.MaxRequestBytes != 1<<20 {
		t.Fatalf("unexpected limit defaults: %+v", cfg)
	}

	values["SQL_JUDGE_REQUEST_TIMEOUT"] = "7s"
	values["SQL_JUDGE_QUERY_TIMEOUT"] = "2s"
	values["SQL_JUDGE_MAX_CONCURRENT"] = "8"
	values["SQL_JUDGE_MAX_RESULT_ROWS"] = "250"
	cfg, err = loadConfig(getenv)
	if err != nil {
		t.Fatalf("loadConfig() override error = %v", err)
	}
	if cfg.RequestTimeout != 7*time.Second || cfg.QueryTimeout != 2*time.Second || cfg.MaxConcurrent != 8 || cfg.MaxResultRows != 250 {
		t.Fatalf("overrides not applied: %+v", cfg)
	}
}

func TestLoadConfigRejectsUnsafeValues(t *testing.T) {
	tests := []map[string]string{
		{},
		{"MYSQL_ROOT_PASSWORD": "secret", "SQL_JUDGE_MAX_CONCURRENT": "0"},
		{"MYSQL_ROOT_PASSWORD": "secret", "SQL_JUDGE_REQUEST_TIMEOUT": "2s", "SQL_JUDGE_QUERY_TIMEOUT": "3s"},
		{"MYSQL_ROOT_PASSWORD": "secret", "SQL_JUDGE_REQUEST_TIMEOUT": "8s", "SQL_JUDGE_QUERY_TIMEOUT": "3s", "SQL_JUDGE_CLEANUP_TIMEOUT": "2s"},
		{"MYSQL_ROOT_PASSWORD": "secret", "SQL_JUDGE_MAX_REQUEST_BYTES": "invalid"},
	}
	for _, values := range tests {
		_, err := loadConfig(func(name string) string { return values[name] })
		if err == nil {
			t.Fatalf("loadConfig(%v) unexpectedly succeeded", values)
		}
	}
}

func TestTemporaryNamesFitMySQLLimits(t *testing.T) {
	databaseName, err := randomName(temporaryDatabasePrefix, 16)
	if err != nil {
		t.Fatal(err)
	}
	userName, err := randomName(temporaryUserPrefix, 8)
	if err != nil {
		t.Fatal(err)
	}
	if !temporaryDatabasePattern.MatchString(databaseName) || len(databaseName) > 64 {
		t.Fatalf("invalid temporary database name %q", databaseName)
	}
	if !temporaryUserPattern.MatchString(userName) || len(userName) > 32 {
		t.Fatalf("invalid temporary user name %q", userName)
	}
	if strings.Contains(quoteIdentifier(databaseName), "'") || strings.Contains(quoteAccount(userName), "`") {
		t.Fatal("temporary name quoting mixed SQL literal and identifier delimiters")
	}
}
