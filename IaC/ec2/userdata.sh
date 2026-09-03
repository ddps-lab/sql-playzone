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
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/logins.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "logins",
            "timezone": "Local"
          },
          {
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/registrations.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "registrations",
            "timezone": "Local"
          },
          {
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/submissions.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "submissions",
            "timezone": "Local"
          },
          {
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/error.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "error",
            "timezone": "Local"
          },
          {
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/sql-judge.log",
            "log_group_name": "${APPLICATION_LOG_GROUP_NAME}",
            "log_stream_name": "sql-judge",
            "timezone": "Local"
          },
          {
            "file_path": "/opt/sql-playzone/platform/.data/CTFd/logs/sql_challenge_behavior.log",
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


cd /opt/sql-playzone/platform

# Load application and database credentials from Secrets Manager
application_secret_file=$(mktemp)
rds_secret_file=$(mktemp)
chmod 600 "$application_secret_file" "$rds_secret_file"
trap 'rm -f "$application_secret_file" "$rds_secret_file"' EXIT

if ! aws secretsmanager get-secret-value \
    --region ${REGION} \
    --secret-id ${APPLICATION_SECRET_NAME} \
    --query SecretString \
    --output text > "$application_secret_file"; then
    exit 1
fi

if ! aws secretsmanager get-secret-value \
    --region ${REGION} \
    --secret-id ${RDS_MASTER_SECRET_ARN} \
    --query SecretString \
    --output text > "$rds_secret_file"; then
    exit 1
fi

python3 - "$application_secret_file" "$rds_secret_file" << 'PY'
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import quote_plus

application_secret = json.loads(Path(sys.argv[1]).read_text())
rds_secret = json.loads(Path(sys.argv[2]).read_text())

env_values = {
    "DATABASE_URL": (
        "mysql+pymysql://"
        f"{quote_plus(rds_secret['username'])}:"
        f"{quote_plus(rds_secret['password'])}"
        "@${RDS_ENDPOINT}/ctfd"
    ),
    "SECRET_KEY": application_secret["CTFD_SECRET_KEY"],
    # Uploads go to S3 through the instance role so they survive instance
    # replacement and are shared by every instance in the ASG.
    "UPLOAD_PROVIDER": "s3",
    "AWS_S3_BUCKET": "${UPLOAD_BUCKET_NAME}",
    "AWS_S3_REGION": "${REGION}",
    # Download links are presigned URLs. With boto3's default addressing they
    # point at the global host (bucket.s3.amazonaws.com), which S3 answers
    # with a redirect to the regional host for a bucket outside us-east-1;
    # the redirected request no longer matches the signature, so every
    # attachment download fails with 403. Virtual addressing signs the
    # regional host directly.
    "AWS_S3_ADDRESSING_STYLE": "virtual",
    "REDIS_URL": "rediss://${ELASTICACHE_ENDPOINT}:6379",
    "WORKERS": "1",
    "LOG_FOLDER": "/var/log/CTFd",
    "ACCESS_LOG": "/var/log/CTFd/access.log",
    "ERROR_LOG": "/var/log/CTFd/error.log",
    "REVERSE_PROXY": "true",
    "SQL_JUDGE_SERVER_URL": "http://sql-judge:8080",
    "GOOGLE_CLIENT_ID": application_secret["GOOGLE_CLIENT_ID"],
    "GOOGLE_CLIENT_SECRET": application_secret["GOOGLE_CLIENT_SECRET"],
    # Optional: the Google Workspace domain allowed to sign in (hanyang.ac.kr
    # when absent).
    "GOOGLE_HOSTED_DOMAIN": application_secret.get("GOOGLE_HOSTED_DOMAIN", ""),
    "CTFD_IMAGE": "${CTFD_IMAGE}",
    "SQL_JUDGE_IMAGE": "${SQL_JUDGE_IMAGE}",
}

env_path = Path(".env")
lines = env_path.read_text().splitlines() if env_path.exists() else []
stale_keys = {"UPLOAD_FOLDER"}
lines = [line for line in lines if line.partition("=")[0] not in env_values | stale_keys]
lines.extend(f"{key}={value}" for key, value in env_values.items())
env_path.write_text("\n".join(lines) + "\n")

judge_env_path = Path(".env.judge")
judge_lines = judge_env_path.read_text().splitlines() if judge_env_path.exists() else []
existing_judge_values = {}
for line in judge_lines:
    key, separator, value = line.partition("=")
    if separator:
        existing_judge_values[key] = value

judge_env_values = {
    "MYSQL_HOST": "mysql-judge",
    "MYSQL_PORT": "3306",
    "MYSQL_ROOT_PASSWORD": existing_judge_values.get("MYSQL_ROOT_PASSWORD") or secrets.token_hex(32),
}
judge_lines = [line for line in judge_lines if line.partition("=")[0] not in judge_env_values]
judge_lines.extend(f"{key}={value}" for key, value in judge_env_values.items())
judge_env_path.write_text("\n".join(judge_lines) + "\n")
PY
chmod 600 .env .env.judge

rm -f "$application_secret_file" "$rds_secret_file"
trap - EXIT

# Login to ECR
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Pull the private release images and start the preloaded production bundle.
docker pull "${CTFD_IMAGE}"
docker pull "${SQL_JUDGE_IMAGE}"
docker compose -f docker-compose.yml up --pull never -d
