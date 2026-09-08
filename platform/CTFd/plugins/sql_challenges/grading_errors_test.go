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
		{"unknown even with familiar message", &mysql.MySQLError{Number: 1105, SQLState: [5]byte{'H', 'Y', '0', '0', '0'}, Message: "No tables used"}},
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
		if got := studentQueryError(tc.err); got != tc.student {
			t.Fatalf("%v: student=%v", tc.err, got)
		}
	}
}
