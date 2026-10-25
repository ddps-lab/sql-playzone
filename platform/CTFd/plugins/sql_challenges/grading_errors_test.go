package main

import (
	"context"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	mysql "github.com/go-sql-driver/mysql"
)

func TestInfrastructureErrorsRemainUngraded(t *testing.T) {
	for _, tc := range []struct {
		name string
		err  error
	}{
		{"connection lost", driver.ErrBadConn},
		{"engine failure", &mysql.MySQLError{Number: 1030, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}}},
		{"request cancelled", context.Canceled},
		{"request deadline", context.DeadlineExceeded},
		{"connection capacity", &mysql.MySQLError{Number: 1040, SQLState: [5]byte{'0', '8', '0', '0', '4'}}},
		{"disk full", &mysql.MySQLError{Number: 1021, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}}},
		{"table full", &mysql.MySQLError{Number: 1114, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}}},
		{"memory exhausted", &mysql.MySQLError{Number: 1037, SQLState: [5]byte{'H', 'Y', '0', '0', '1'}}},
		{"shutdown", &mysql.MySQLError{Number: 1053, SQLState: [5]byte{'0', '8', 'S', '0', '1'}}},
		{"user resource limit despite syntax state", &mysql.MySQLError{Number: 1226, SQLState: [5]byte{'4', '2', '0', '0', '0'}}},
		{"lock timeout", &mysql.MySQLError{Number: 1205, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}}},
		{"deadlock", &mysql.MySQLError{Number: 1213, SQLState: [5]byte{'4', '0', '0', '0', '1'}}},
		{"killed session", &mysql.MySQLError{Number: 3169, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := classifyQueryError(fmt.Errorf("query error: %w", tc.err))
			if got := gradingErrorKind(err); got != "system" {
				t.Fatalf("student execution: kind=%q, want system", got)
			}
			if got := gradingErrorKind(problemError(err)); got != "system" {
				t.Fatalf("reference execution: kind=%q, want system", got)
			}
		})
	}
}

func TestOnlyStudentQueryErrorsArePenalized(t *testing.T) {
	for _, tc := range []struct {
		err     error
		student bool
	}{
		{&mysql.MySQLError{Number: 1054, SQLState: [5]byte{'4', '2', 'S', '2', '2'}}, true},
		{&mysql.MySQLError{Number: 3024}, true},
		{errResultLimit, true},
		{&mysql.MySQLError{Number: 1040, SQLState: [5]byte{'0', '8', '0', '0', '4'}}, false},
		{errors.New("connection lost"), false},
		{context.DeadlineExceeded, false},
	} {
		if got := gradingErrorKind(classifyQueryError(tc.err)) == "student_query"; got != tc.student {
			t.Fatalf("%v: student=%v", tc.err, got)
		}
	}
}

func TestMySQLQueryErrorsPassThroughWithoutAStudentErrorList(t *testing.T) {
	for _, tc := range []struct {
		code  uint16
		state string
	}{
		{1353, "HY000"},  // CTE column count
		{3065, "HY000"},  // DISTINCT / ORDER BY
		{1525, "HY000"},  // invalid DATE literal
		{3029, "HY000"},  // aggregate in nonaggregated ORDER BY
		{1235, "42000"},  // unsupported query feature: preserve MySQL explanation
		{60002, "0A000"}, // preserve the existing default for SQL error packets
		{1096, "HY000"},  // no tables
		{1111, "HY000"},  // invalid aggregate
		{1052, "23000"},  // ambiguous column
		{1242, "21000"},  // scalar subquery returns multiple rows
		{3696, "HY000"},  // invalid regular expression
		{1105, "HY000"},  // generic MySQL error packet
		{60000, "HY000"}, // a code the judge has never enumerated
		{60001, "ZZ999"}, // a state the judge has never enumerated
	} {
		t.Run(fmt.Sprint(tc.code), func(t *testing.T) {
			var state [5]byte
			copy(state[:], tc.state)
			original := fmt.Errorf("query error: %w", &mysql.MySQLError{
				Number: tc.code, SQLState: state, Message: "original MySQL detail",
			})
			classified := classifyQueryError(original)
			if gradingErrorKind(classified) != "student_query" || classified.Error() != original.Error() {
				t.Fatalf("MySQL query error was not passed through: %v", classified)
			}
			if !errors.Is(classified, original) {
				t.Fatal("original cause was lost")
			}
			if gradingErrorKind(problemError(classified)) != "problem" {
				t.Fatal("reference query error was assigned to the student")
			}
		})
	}
}

func TestSetupErrorsAreNotReclassifiedAsQueryErrors(t *testing.T) {
	// MySQL may return a familiar SQL error while the judge configures a session.
	// Only the SQL execution boundary may attribute it to the submitted query.
	for _, phase := range []string{"connect isolated MySQL user", "set query execution limit", "read init session sql_mode"} {
		err := fmt.Errorf("%s: %w", phase, &mysql.MySQLError{
			Number: 1054, SQLState: [5]byte{'4', '2', 'S', '2', '2'}, Message: "Unknown column",
		})
		if gradingErrorKind(err) != "system" || gradingErrorKind(problemError(err)) != "system" {
			t.Fatalf("setup failure was attributed to SQL: %v", err)
		}
	}
}

func TestFailureDiagnosticsDoNotChangeTheVerdict(t *testing.T) {
	for _, tc := range []struct {
		name    string
		err     error
		kind    string
		number  uint16
		timeout bool
	}{
		{"engine", classifyQueryError(&mysql.MySQLError{Number: 1030, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}, Message: "engine detail"}), "system", 1030, false},
		{"deadline", context.DeadlineExceeded, "system", 0, true},
		{"cancelled", context.Canceled, "system", 0, false},
		{"connection", driver.ErrBadConn, "system", 0, false},
		{"unsupported SQL", classifyQueryError(&mysql.MySQLError{Number: 1235, Message: "LIMIT & IN subquery"}), "student_query", 1235, false},
		{"MySQL timeout", classifyQueryError(&mysql.MySQLError{Number: 3024, Message: "maximum statement execution time exceeded"}), "student_query", 3024, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := gradingFailure(tc.err)
			if r.Success || r.ErrorKind != tc.kind || r.MySQLNumber != tc.number || r.Error != tc.err.Error() {
				t.Fatalf("diagnostics changed verdict/cause: %+v", r)
			}
			b, _ := json.Marshal(r)
			var metadata map[string]interface{}
			json.Unmarshal(b, &metadata)
			if (metadata["deadline_exceeded"] == true) != tc.timeout {
				t.Fatalf("deadline metadata lost: %s", b)
			}
			if _, ok := metadata["error_code"]; ok {
				t.Fatalf("unnecessary public taxonomy remains: %s", b)
			}
		})
	}
}

func TestDeadlineCauseRecognizesConnectionsClosedAtTheDeadline(t *testing.T) {
	expired, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	closed := fmt.Errorf("query error: %w", mysql.ErrInvalidConn)
	if err := deadlineCause(expired, closed); !errors.Is(err, context.DeadlineExceeded) || !errors.Is(err, mysql.ErrInvalidConn) ||
		gradingErrorKind(err) != "system" || !gradingFailure(err).DeadlineExceeded {
		t.Fatalf("connection closed at the deadline lost its cause: %v", err)
	}
	if err := deadlineCause(context.Background(), closed); errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("connection failure without a deadline was labeled a deadline: %v", err)
	}
	timeout := classifyQueryError(&mysql.MySQLError{Number: 3024})
	if err := deadlineCause(expired, timeout); err != timeout {
		t.Fatalf("student verdict changed: %v", err)
	}
}
