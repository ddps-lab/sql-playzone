#!/bin/bash

# Update and install dependencies
# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$${UBUNTU_CODENAME:-$$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker service
systemctl start docker
systemctl enable docker

# Install AWS CLI and cloudwatch-agent
sudo snap install aws-cli --classic # cloud watch agent included
SYSTEM_ARCH=$(dpkg --print-architecture)
wget -q https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/$${SYSTEM_ARCH}/latest/amazon-cloudwatch-agent.deb
dpkg -i -E ./amazon-cloudwatch-agent.deb
rm amazon-cloudwatch-agent.deb

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
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/*.log",
            "log_group_name": "/aws/ec2/sql-playzone/production",
            "log_stream_name": "ctfd-combined",
            "timezone": "Local",
            "timestamp_format": "[%d/%m/%Y %H:%M:%S]",
            "multi_line_start_pattern": "^\\[\\d{2}/\\d{2}/\\d{4}"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/access.log",
            "log_group_name": "/aws/ec2/sql-playzone/production",
            "log_stream_name": "ctfd-access",
            "timezone": "Local"
          },
          {
            "file_path": "/home/ubuntu/sql-playzone/platform/.data/CTFd/logs/error.log",
            "log_group_name": "/aws/ec2/sql-playzone/production",
            "log_stream_name": "ctfd-error",
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

# Enable CloudWatch Agent to start on boot
systemctl enable amazon-cloudwatch-agent




# Clone the repository
cd /home/ubuntu
git clone https://github.com/ddps-lab/sql-playzone.git

cd sql-playzone/platform/CTFd
cp config.example.ini config.ini
cd ..

# Create .env file with database configuration
cat > .env << EOF
DATABASE_URL=mysql+pymysql://${DB_USERNAME}:${DB_PASSWORD}@${RDS_ENDPOINT}/ctfd
SECRET_KEY=${CTFD_SECRET_KEY}
UPLOAD_FOLDER=${UPLOAD_FOLDER}
REDIS_URL=${REDIS_URL}
WORKERS=${WORKERS}
LOG_FOLDER=${LOG_FOLDER}
ACCESS_LOG=${ACCESS_LOG}
ERROR_LOG=${ERROR_LOG}
REVERSE_PROXY=${REVERSE_PROXY}
SQL_JUDGE_SERVER_URL=${SQL_JUDGE_SERVER_URL}
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
EOF

# Run docker-compose
docker compose build
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

docker tag platform-sql-judge:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-sql-judge:latest
docker tag platform-ctfd:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-ctfd:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-sql-judge:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/platform-ctfd:latest

docker rmi -f $(docker images -aq)