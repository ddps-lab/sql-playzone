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
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "logins",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/registrations.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "registrations",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/submissions.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "submissions",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/error.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "error",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/sql-judge.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "sql-judge",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/sql_challenge_behavior.log",
            "log_group_name": "${BEHAVIOR_LOG_GROUP_NAME}",
            "log_stream_name": "${BEHAVIOR_LOG_STREAM_NAME}",
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

# Runtime credentials must be refreshed on every ASG instance launch.
sed -i '/^GOOGLE_CLIENT_ID=/d; /^GOOGLE_CLIENT_SECRET=/d' .env
{
  printf 'GOOGLE_CLIENT_ID=%s\n' "$(printf '%s' '${GOOGLE_CLIENT_ID_B64}' | base64 --decode)"
  printf 'GOOGLE_CLIENT_SECRET=%s\n' "$(printf '%s' '${GOOGLE_CLIENT_SECRET_B64}' | base64 --decode)"
} >> .env

# Login to ECR
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Pull images from ECR
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SQL_JUDGE_ECR_REPOSITORY_NAME}:latest
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${CTFD_ECR_REPOSITORY_NAME}:latest

# Tag the pulled images with local names that docker-compose expects
docker tag ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SQL_JUDGE_ECR_REPOSITORY_NAME}:latest platform-sql-judge:latest
docker tag ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${CTFD_ECR_REPOSITORY_NAME}:latest platform-ctfd:latest

# Run docker-compose
docker compose up -d
