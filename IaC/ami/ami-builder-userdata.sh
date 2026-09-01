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
# Enable CloudWatch Agent to start on boot
systemctl enable amazon-cloudwatch-agent

# Clone the repository
cd /home/ubuntu
git clone https://github.com/ddps-lab/sql-playzone.git

cd sql-playzone/platform/CTFd
cp config.example.ini config.ini
cd ..

# docker compose expects the env file to exist while building the images.
touch .env
chmod 600 .env

# Run docker-compose
docker compose build
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

docker tag platform-sql-judge:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SQL_JUDGE_ECR_REPOSITORY_NAME}:latest
docker tag platform-ctfd:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${CTFD_ECR_REPOSITORY_NAME}:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${SQL_JUDGE_ECR_REPOSITORY_NAME}:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${CTFD_ECR_REPOSITORY_NAME}:latest

docker rmi -f $(docker images -aq)
