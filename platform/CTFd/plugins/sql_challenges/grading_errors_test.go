package main

import (
	"context"
	"database/sql/driver"
	"errors"
	"fmt"
	"testing"

	mysql "github.com/go-sql-driver/mysql"
)

func TestInfrastructureErrorsRemainUngraded(t *testing.T) {
	for _, tc := range []struct {
		name string
		err  error
	}{
		{"connection lost", driver.ErrBadConn},
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
