//go:build integration

package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	mysql "github.com/go-sql-driver/mysql"
)

func integrationServer(t *testing.T) *Server {
	t.Helper()
	cfg, err := loadConfig(os.Getenv)
	if err != nil {
		t.Fatal(err)
	}
	cfg.StartupTimeout = 30 * time.Second
	cfg.QueryTimeout = 2 * time.Second
	cfg.RequestTimeout = 7 * time.Second
	cfg.CleanupTimeout = 2 * time.Second
	server, err := newServer(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { server.controlDB.Close() })
	return server
}

func TestIntegrationJudgeContractAndMySQLDDL(t *testing.T) {
	server := integrationServer(t)
	request := QueryRequest{
		InitQuery: `
CREATE TABLE parents (id INT PRIMARY KEY, name VARCHAR(20));
CREATE TABLE children (id INT PRIMARY KEY, parent_id INT, FOREIGN KEY (parent_id) REFERENCES parents(id));
INSERT INTO parents VALUES (1, 'Alice'), (2, 'Bob');
INSERT INTO children VALUES (10, 1), (20, 2);`,
		SolutionQuery: "SELECT p.name FROM parents p JOIN children c ON c.parent_id = p.id ORDER BY c.id",
		UserQuery:     "SELECT name AS different_alias FROM parents ORDER BY id",
	}
	body, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	recorder := httptest.NewRecorder()
	server.routes().ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/judge", bytes.NewReader(body)))
	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
	var response QueryResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	if !response.Success || !response.Match {
		t.Fatalf("unexpected response: %+v", response)
	}
	if strings.Join(response.UserResult.Rows[0], ",") != "Alice" {
		t.Fatalf("unexpected user rows: %#v", response.UserResult.Rows)
	}
}

func TestIntegrationBuiltContainerEndpoint(t *testing.T) {
	baseURL := os.Getenv("SQL_JUDGE_CONTAINER_URL")
	if baseURL == "" {
		t.Skip("SQL_JUDGE_CONTAINER_URL is not set")
	}
	request := QueryRequest{
		InitQuery:     "CREATE TABLE items (id INT PRIMARY KEY, label VARCHAR(20)); INSERT INTO items VALUES (1, 'one'), (2, 'two');",
		SolutionQuery: "SELECT label FROM items ORDER BY id",
		UserQuery:     "SELECT label FROM items ORDER BY id",
	}
	body, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	response, err := http.Post(baseURL+"/judge", "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	var result QueryResponse
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK || !result.Success || !result.Match {
		t.Fatalf("status=%d result=%+v", response.StatusCode, result)
	}
}

func TestIntegrationResultFormattingAndOrder(t *testing.T) {
	server := integrationServer(t)
	result, err := server.executeQuery(context.Background(), []string{
		"CREATE TABLE values_table (id INT, amount DECIMAL(8,2), day DATE, moment DATETIME, ratio FLOAT, optional_value INT);" +
			"INSERT INTO values_table VALUES (2, 12.30, '2026-09-01', '2026-09-01 12:34:56', 1.5, NULL)," +
			"(1, 7.00, '2026-08-31', '2026-08-31 01:02:03', 2.25, 9);",
	}, "SELECT id, amount, day, moment, ratio, optional_value FROM values_table ORDER BY id", nil)
	if err != nil {
		t.Fatal(err)
	}
	want := [][]string{
		{"1", "7.00", "2026-08-31", "2026-08-31 01:02:03", "2.25", "9"},
		{"2", "12.30", "2026-09-01", "2026-09-01 12:34:56", "1.5", "NULL"},
	}
	if !rowsEqual(result.Rows, want) {
		t.Fatalf("rows = %#v, want %#v", result.Rows, want)
	}
}

func TestIntegrationTemporaryUserCannotCrossDatabaseBoundary(t *testing.T) {
	server := integrationServer(t)
	databaseA, _ := randomName(temporaryDatabasePrefix, 16)
	userA, _ := randomName(temporaryUserPrefix, 8)
	passwordA, _ := randomHex(32)
	databaseB, _ := randomName(temporaryDatabasePrefix, 16)
	userB, _ := randomName(temporaryUserPrefix, 8)
	passwordB, _ := randomHex(32)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.createExecutionResources(ctx, databaseA, userA, passwordA); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { server.cleanupExecution(databaseA, userA) })
	if err := server.createExecutionResources(ctx, databaseB, userB, passwordB); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { server.cleanupExecution(databaseB, userB) })

	db := openIntegrationUser(t, server.config, userA, passwordA, databaseA)
	defer db.Close()
	if _, err := db.ExecContext(ctx, "CREATE TABLE own_table (id INT)"); err != nil {
		t.Fatalf("own database access failed: %v", err)
	}
	if _, err := db.ExecContext(ctx, "CREATE TABLE "+quoteIdentifier(databaseB)+".forbidden (id INT)"); err == nil {
		t.Fatal("temporary user accessed another execution database")
	}
	if _, err := db.QueryContext(ctx, "SELECT User FROM mysql.user"); err == nil {
		t.Fatal("temporary user accessed mysql.user")
	}
}

func TestIntegrationRejectsMultipleStatementsAndResultOverflow(t *testing.T) {
	server := integrationServer(t)
	if _, err := server.executeQuery(context.Background(), nil, "SELECT 1; SELECT 2", nil); err == nil {
		t.Fatal("multiple statements unexpectedly succeeded")
	}
	server.config.MaxResultRows = 2
	_, err := server.executeQuery(context.Background(), []string{
		"CREATE TABLE many_rows (id INT); INSERT INTO many_rows VALUES (1), (2), (3);",
	}, "SELECT id FROM many_rows ORDER BY id", nil)
	if !errors.Is(err, errResultLimit) {
		t.Fatalf("row overflow error = %v, want errResultLimit", err)
	}
}

func TestIntegrationQueryTimeoutAndCleanup(t *testing.T) {
	server := integrationServer(t)
	server.config.QueryTimeout = 100 * time.Millisecond
	started := time.Now()
	_, err := server.executeQuery(context.Background(), nil,
		"SELECT COUNT(*) FROM information_schema.columns a CROSS JOIN information_schema.columns b CROSS JOIN information_schema.columns c", nil)
	if err == nil {
		t.Fatal("expensive query unexpectedly succeeded")
	}
	if time.Since(started) > 2*time.Second {
		t.Fatalf("query timeout took too long: %s", time.Since(started))
	}

	time.Sleep(100 * time.Millisecond)
	assertNoTemporaryResources(t, server)
}

func TestIntegrationStartupSweeperRemovesOrphans(t *testing.T) {
	server := integrationServer(t)
	databaseName, _ := randomName(temporaryDatabasePrefix, 16)
	userName, _ := randomName(temporaryUserPrefix, 8)
	password, _ := randomHex(32)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.createExecutionResources(ctx, databaseName, userName, password); err != nil {
		t.Fatal(err)
	}
	if err := server.cleanupStaleResources(ctx); err != nil {
		t.Fatal(err)
	}
	assertNoTemporaryResources(t, server)
}

func TestIntegrationSweeperPreservesLiveExecution(t *testing.T) {
	server := integrationServer(t)
	databaseName, _ := randomName(temporaryDatabasePrefix, 16)
	userName, _ := randomName(temporaryUserPrefix, 8)
	password, _ := randomHex(32)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.createExecutionResources(ctx, databaseName, userName, password); err != nil {
		t.Fatal(err)
	}
	server.markExecutionLive(databaseName, userName)
	if err := server.cleanupStaleResources(ctx); err != nil {
		t.Fatal(err)
	}
	db := openIntegrationUser(t, server.config, userName, password, databaseName)
	db.Close()

	server.unmarkExecutionLive(databaseName, userName)
	if err := server.cleanupStaleResources(ctx); err != nil {
		t.Fatal(err)
	}
	assertNoTemporaryResources(t, server)
}

func openIntegrationUser(t *testing.T, cfg Config, user, password, database string) *sql.DB {
	t.Helper()
	driverConfig := mysql.NewConfig()
	driverConfig.User = user
	driverConfig.Passwd = password
	driverConfig.Net = "tcp"
	driverConfig.Addr = net.JoinHostPort(cfg.MySQLHost, cfg.MySQLPort)
	driverConfig.DBName = database
	db, err := sql.Open("mysql", driverConfig.FormatDSN())
	if err != nil {
		t.Fatal(err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		t.Fatal(err)
	}
	return db
}

func assertNoTemporaryResources(t *testing.T, server *Server) {
	t.Helper()
	var databaseCount int
	if err := server.controlDB.QueryRow(
		"SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME REGEXP '^ctfd_tmp_[0-9a-f]{32}$'",
	).Scan(&databaseCount); err != nil {
		t.Fatal(err)
	}
	var userCount int
	if err := server.controlDB.QueryRow(
		"SELECT COUNT(*) FROM mysql.user WHERE User REGEXP '^ct_[0-9a-f]{16}$'",
	).Scan(&userCount); err != nil {
		t.Fatal(err)
	}
	if databaseCount != 0 || userCount != 0 {
		t.Fatalf("temporary resources remain: databases=%d users=%d", databaseCount, userCount)
	}
	var processCount int
	if err := server.controlDB.QueryRow(
		"SELECT COUNT(*) FROM INFORMATION_SCHEMA.PROCESSLIST WHERE USER REGEXP '^ct_[0-9a-f]{16}$'",
	).Scan(&processCount); err != nil {
		t.Fatal(err)
	}
	if processCount != 0 {
		t.Fatalf("temporary user processes remain: %d", processCount)
	}
}

func rowsEqual(left, right [][]string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if strings.Join(left[index], "\x00") != strings.Join(right[index], "\x00") {
			return false
		}
	}
	return true
}
