package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math/big"
	"strconv"
	"strings"
)

// Policy describes the public problem contract, using one-based output columns.
// No order keys means a bag of rows: duplicates count, incidental order does not.
type OrderKey struct {
	Column    int    `json:"column"`
	Direction string `json:"direction"`
}
type GradingPolicy struct {
	Version            int        `json:"version"`
	OrderBy            []OrderKey `json:"order_by"`
	ExactFormatColumns []int      `json:"exact_format_columns"`
}

func (p GradingPolicy) validate(columns int) error {
	if p.Version != 0 && p.Version != 1 {
		return fmt.Errorf("unsupported grading policy version")
	}
	seen := map[int]bool{}
	for _, key := range p.OrderBy {
		if key.Column < 1 || key.Column > columns || seen[key.Column] || (key.Direction != "asc" && key.Direction != "desc") {
			return fmt.Errorf("invalid grading order key")
		}
		seen[key.Column] = true
	}
	seen = map[int]bool{}
	for _, col := range p.ExactFormatColumns {
		if col < 1 || col > columns || seen[col] {
			return fmt.Errorf("invalid grading format column")
		}
		seen[col] = true
	}
	return nil
}

// Keep driver text for exact decimal arithmetic; JSON null remains distinct from
// the string "NULL". We never turn DECIMAL/BIGINT into a JavaScript float.
func (r QueryResult) MarshalJSON() ([]byte, error) {
	rows := make([][]any, len(r.Rows))
	for i, row := range r.Rows {
		rows[i] = make([]any, len(row))
		for j, value := range row {
			if !r.isNull(i, j) {
				rows[i][j] = value
			}
		}
	}
	return json.Marshal(struct {
		Columns     []string `json:"columns"`
		Rows        [][]any  `json:"rows"`
		RowCount    int      `json:"row_count"`
		ColumnTypes []string `json:"column_types,omitempty"`
		Nulls       [][]bool `json:"nulls,omitempty"`
	}{r.Columns, rows, r.RowCount, r.ColumnTypes, r.Nulls})
}
func (r *QueryResult) isNull(i, j int) bool {
	return i < len(r.Nulls) && j < len(r.Nulls[i]) && r.Nulls[i][j]
}
func numericType(t string) bool {
	switch strings.TrimPrefix(t, "UNSIGNED ") {
	case "TINYINT", "SMALLINT", "MEDIUMINT", "INT", "BIGINT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE":
		return true
	}
	return false
}
func rowKey(r *QueryResult, index int, p GradingPolicy) string {
	values := make([][2]string, len(r.Rows[index]))
	for col, value := range r.Rows[index] {
		if r.isNull(index, col) {
			values[col] = [2]string{"null", ""}
			continue
		}
		exact := false
		for _, position := range p.ExactFormatColumns {
			if position == col+1 {
				exact = true
			}
		}
		kind := "text"
		if !exact && col < len(r.ColumnTypes) && numericType(r.ColumnTypes[col]) {
			kind = "number"
			if number, ok := new(big.Rat).SetString(value); ok {
				value = number.RatString()
			}
		}
		values[col] = [2]string{kind, value}
	}
	data, _ := json.Marshal(values)
	return string(data)
}
func compareGradedResults(expected, actual *QueryResult, p GradingPolicy, ranks []string) bool {
	if len(expected.Columns) != len(actual.Columns) || len(expected.Rows) != len(actual.Rows) {
		return false
	}
	for _, row := range actual.Rows {
		if len(row) != len(actual.Columns) {
			return false
		}
	}
	if len(p.OrderBy) > 0 && len(ranks) != len(expected.Rows) {
		return false
	}
	for start := 0; start < len(expected.Rows); {
		end := len(expected.Rows)
		if len(p.OrderBy) > 0 {
			end = start + 1
			for end < len(ranks) && ranks[end] == ranks[start] {
				end++
			}
		}
		counts := map[string]int{}
		for i := start; i < end; i++ {
			counts[rowKey(expected, i, p)]++
			counts[rowKey(actual, i, p)]--
		}
		for _, count := range counts {
			if count != 0 {
				return false
			}
		}
		start = end
	}
	return true
}
func problemError(err error) error {
	if gradingErrorKind(err) == "student_query" || studentQueryError(err) {
		return &gradingError{kind: "problem", cause: err}
	}
	return err
}

// Both answers see one initialized database and separate read-only connections.
// MySQL supplies tie groups, including its NULL ordering and column collation.
func (s *Server) judgeQueries(parent context.Context, req *QueryRequest) (expected, actual *QueryResult, ranks []string, err error) {
	if err = validateSQLQuery(req.SolutionQuery, req); err != nil {
		err = &gradingError{kind: "problem", cause: err}
		return
	}
	resources, e := newExecutionResources()
	if e != nil {
		err = e
		return
	}
	s.markExecutionLive(resources)
	defer func() { s.cleanupExecution(resources); s.unmarkExecutionLive(resources) }()
	refCtx, cancel := context.WithTimeout(parent, s.config.QueryTimeout)
	defer cancel()
	if err = s.createExecutionResources(refCtx, resources); err != nil {
		return
	}
	session, e := s.runInitStatements(refCtx, resources, []string{req.InitQuery}, req)
	if e != nil {
		err = problemError(e)
		return
	}
	expected, err = s.runGradedQuery(refCtx, resources, req.SolutionQuery, session)
	if err != nil {
		err = problemError(err)
		return
	}
	if e = req.GradingPolicy.validate(len(expected.Columns)); e != nil {
		err = &gradingError{kind: "problem", cause: e}
		return
	}
	if len(req.GradingPolicy.OrderBy) > 0 {
		aliases := make([]string, len(expected.Columns))
		for i := range aliases {
			aliases[i] = "c" + strconv.Itoa(i)
		}
		keys := make([]string, len(req.GradingPolicy.OrderBy))
		for i, key := range req.GradingPolicy.OrderBy {
			keys[i] = "r." + aliases[key.Column-1] + " " + key.Direction
		}
		ordering := strings.Join(keys, ",")
		query := "SELECT r.*, DENSE_RANK() OVER (ORDER BY " + ordering + ") AS ctfd_rank FROM (\n" + strings.TrimSuffix(strings.TrimSpace(req.SolutionQuery), ";") + "\n) AS r(" + strings.Join(aliases, ",") + ") ORDER BY " + ordering
		ranked, e := s.runGradedQuery(refCtx, resources, query, session)
		if e != nil {
			err = problemError(e)
			return
		}
		width := len(expected.Columns)
		for i, row := range ranked.Rows {
			ranks = append(ranks, row[width])
			ranked.Rows[i] = row[:width]
			ranked.Nulls[i] = ranked.Nulls[i][:width]
		}
		ranked.Columns = expected.Columns
		ranked.ColumnTypes = ranked.ColumnTypes[:width]
		bag := req.GradingPolicy
		bag.OrderBy = nil
		if !compareGradedResults(expected, ranked, bag, nil) {
			err = &gradingError{kind: "problem", cause: fmt.Errorf("reference query is not deterministic")}
			return
		}
		expected = ranked
	}
	cancel()
	if e = validateSQLQuery(req.UserQuery, req); e != nil {
		err = &gradingError{kind: "student_query", cause: e}
		return
	}
	userCtx, userCancel := context.WithTimeout(parent, s.config.QueryTimeout)
	defer userCancel()
	actual, err = s.runGradedQuery(userCtx, resources, req.UserQuery, session)
	return
}
