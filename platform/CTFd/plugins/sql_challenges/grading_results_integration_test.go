//go:build integration

package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func TestIntegrationPublicGradingContract(t *testing.T) {
	server := integrationServer(t)
	for _, tc := range []struct {
		name, init, reference, student string
		policy                         GradingPolicy
		match                          bool
	}{
		{"numeric scale", "", "SELECT CAST(1 AS DECIMAL(20,2))", "SELECT 1", GradingPolicy{}, true},
		{"large integer differs", "", "SELECT 9007199254740993", "SELECT 9007199254740992", GradingPolicy{}, false},
		{"null is not text", "", "SELECT NULL", "SELECT 'NULL'", GradingPolicy{}, false},
		{"null is not empty", "", "SELECT NULL", "SELECT ''", GradingPolicy{}, false},
		{"numeric is not text", "", "SELECT 1", "SELECT '1'", GradingPolicy{}, false},
		{"text preserves whitespace", "", "SELECT 'a '", "SELECT 'a'", GradingPolicy{}, false},
		{"unordered bag", "", "SELECT 1 UNION ALL SELECT 2", "SELECT 2 UNION ALL SELECT 1", GradingPolicy{}, true},
		{"duplicates count", "", "SELECT 1 UNION ALL SELECT 1 UNION ALL SELECT 2", "SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 2", GradingPolicy{}, false},
		{"explicit display", "", "SELECT CAST(1 AS DECIMAL(10,2))", "SELECT 1", GradingPolicy{ExactFormatColumns: []int{1}}, false},
		{"explicit display string", "", "SELECT CAST(1 AS DECIMAL(10,2))", "SELECT '1.00'", GradingPolicy{ExactFormatColumns: []int{1}}, true},
		{"shared generated fixture", "CREATE TABLE t(v VARCHAR(36));INSERT INTO t VALUES(UUID());", "SELECT v FROM t", "SELECT v FROM t", GradingPolicy{}, true},
		{"ties follow mysql collation", "CREATE TABLE t(k VARCHAR(10),v INT);INSERT INTO t VALUES('a',1),('A',2),('b',3);", "SELECT * FROM t ORDER BY k,v", "SELECT * FROM t ORDER BY k,v DESC", GradingPolicy{OrderBy: []OrderKey{{1, "asc"}}}, true},
		{"wrong group order", "CREATE TABLE t(k INT,v INT);INSERT INTO t VALUES(NULL,1),(1,2),(1,3),(2,4);", "SELECT * FROM t ORDER BY k,v", "SELECT * FROM t ORDER BY k DESC,v", GradingPolicy{OrderBy: []OrderKey{{1, "asc"}}}, false},
		{"ties and nulls", "CREATE TABLE t(k INT,v INT);INSERT INTO t VALUES(NULL,1),(NULL,2),(1,3),(1,4);", "SELECT * FROM t ORDER BY k,v", "SELECT * FROM t ORDER BY k,v DESC", GradingPolicy{OrderBy: []OrderKey{{1, "asc"}}}, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			request := QueryRequest{InitQuery: tc.init, SolutionQuery: tc.reference, UserQuery: tc.student, GradingPolicy: tc.policy}
			expected, actual, ranks, err := server.judgeQueries(context.Background(), &request)
			if err != nil {
				t.Fatal(err)
			}
			if got := compareGradedResults(expected, actual, tc.policy, ranks); got != tc.match {
				t.Fatalf("match=%v expected=%+v actual=%+v ranks=%v", got, expected, actual, ranks)
			}
		})
	}
	request := QueryRequest{SolutionQuery: "SELECT NULL,'NULL'", UserQuery: "SELECT NULL,'NULL'"}
	_, actual, _, err := server.judgeQueries(context.Background(), &request)
	if err != nil {
		t.Fatal(err)
	}
	data, err := json.Marshal(actual)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), `"rows":[[null,"NULL"]]`) {
		t.Fatalf("null wire representation: %s", data)
	}
	request = QueryRequest{SolutionQuery: "SELECT UUID()", UserQuery: "SELECT UUID()", GradingPolicy: GradingPolicy{OrderBy: []OrderKey{{1, "asc"}}}}
	_, _, _, err = server.judgeQueries(context.Background(), &request)
	if err == nil || gradingErrorKind(err) != "problem" {
		t.Fatalf("nondeterministic reference: %v", err)
	}
}
