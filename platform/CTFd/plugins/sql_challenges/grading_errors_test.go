package main

import (
	"context"
	"errors"
	mysql "github.com/go-sql-driver/mysql"
	"testing"
)

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
