FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy go mod file
COPY go.mod ./

# Copy source code (needed for go mod tidy to detect dependencies)
COPY sql_judge_server.go .

# Download dependencies and generate go.sum
RUN go mod download && go mod tidy

# Build the application
RUN go build -o sql-judge-server sql_judge_server.go

# Final stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Copy the binary from builder
COPY --from=builder /app/sql-judge-server .

EXPOSE 8080

CMD ["./sql-judge-server"]