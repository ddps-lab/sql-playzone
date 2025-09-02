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