#!/bin/bash
# Configure CloudWatch Agent
cat << 'CWCONFIG' | tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root",
    "buffer_time": 2000,
    "max_buffer_time": 5000
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/logins.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "logins",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/registrations.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "registrations",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/submissions.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "submissions",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/access.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "access",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/error.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "error",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/sql-judge.log",
            "log_group_name": "/aws/ec2/sql-playzone",
            "log_stream_name": "sql-judge",
            "timezone": "Local"
          }
        ]
      }
    },
    "force_flush_interval": 5
  }
}
CWCONFIG

# Start CloudWatch Agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json


cd /home/ubuntu/sql-playzone/platform
git pull origin main

# Login to ECR
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Pull images from ECR
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-sql-judge:latest
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-ctfd:latest

# Tag the pulled images with local names that docker-compose expects
docker tag ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-sql-judge:latest platform-sql-judge:latest
docker tag ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-ctfd:latest platform-ctfd:latest

# Run docker-compose
docker compose up -d