#!/bin/bash

# Build script for SQL Judge Server

echo "Building SQL Judge Server..."

# Navigate to the plugin directory
cd "$(dirname "$0")"

# Download dependencies
echo "Downloading Go dependencies..."
go mod tidy

# Build the server
echo "Building Go server..."
go build -o sql-judge-server sql_judge_server.go

echo "Build complete!"

# Run the server locally (optional)
if [ "$1" == "run" ]; then
    echo "Starting SQL Judge Server..."
    ./sql-judge-server
fi