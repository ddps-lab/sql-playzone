#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
working_directory=$(mktemp -d)
trap 'sudo rm -rf "$working_directory"' EXIT

sudo apt-get update
sudo apt-get install -y ca-certificates curl git unzip
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu

curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "$working_directory/awscliv2.zip"
unzip -q "$working_directory/awscliv2.zip" -d "$working_directory"
sudo "$working_directory/aws/install"

curl -fsSL "https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/arm64/latest/amazon-cloudwatch-agent.deb" -o "$working_directory/amazon-cloudwatch-agent.deb"
sudo dpkg -i "$working_directory/amazon-cloudwatch-agent.deb"
sudo systemctl enable amazon-cloudwatch-agent

sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/* /root/.cache /home/ubuntu/.cache /root/.docker
sudo cloud-init clean --logs
