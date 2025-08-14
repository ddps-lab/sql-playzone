FROM golang:1.21-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY sql_judge_server.go .

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