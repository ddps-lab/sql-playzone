FROM golang:1.24.5-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies before copying source so source-only changes retain this layer.
RUN go mod download

COPY sql_judge_server.go ./

RUN go build -trimpath -o sql-judge-server sql_judge_server.go

# Final stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Copy the binary from builder
COPY --from=builder /app/sql-judge-server .

EXPOSE 8080

CMD ["./sql-judge-server"]
