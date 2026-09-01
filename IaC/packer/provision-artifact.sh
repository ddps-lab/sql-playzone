#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

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

working_directory=$(mktemp -d)
trap 'sudo rm -rf "$working_directory"' EXIT

curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "$working_directory/awscliv2.zip"
unzip -q "$working_directory/awscliv2.zip" -d "$working_directory"
sudo "$working_directory/aws/install"

curl -fsSL "https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/arm64/latest/amazon-cloudwatch-agent.deb" -o "$working_directory/amazon-cloudwatch-agent.deb"
sudo dpkg -i "$working_directory/amazon-cloudwatch-agent.deb"
sudo systemctl enable amazon-cloudwatch-agent

source_directory="$working_directory/source"
git init "$source_directory"
git -C "$source_directory" remote add origin "$REPOSITORY_URL"
git -C "$source_directory" fetch --depth 1 origin "$COMMIT_SHA"
git -C "$source_directory" checkout --detach FETCH_HEAD

actual_commit=$(git -C "$source_directory" rev-parse HEAD)
if [[ "$actual_commit" != "$COMMIT_SHA" ]]; then
  echo "Checked out $actual_commit, expected $COMMIT_SHA" >&2
  exit 1
fi

cp "$source_directory/platform/CTFd/config.example.ini" "$source_directory/platform/CTFd/config.ini"

registry="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
ctfd_tag="$registry/$CTFD_REPOSITORY_NAME:$RELEASE_ID"
sql_judge_tag="$registry/$SQL_JUDGE_REPOSITORY_NAME:$RELEASE_ID"

aws ecr get-login-password --region "$AWS_REGION" | sudo docker login --username AWS --password-stdin "$registry"
sudo docker build --pull --tag "$ctfd_tag" "$source_directory/platform"
sudo docker build --pull --tag "$sql_judge_tag" "$source_directory/platform/CTFd/plugins/sql_challenges"
sudo docker push "$ctfd_tag"
sudo docker push "$sql_judge_tag"

sudo install -d -o ubuntu -g ubuntu /opt/sql-playzone/platform/conf/nginx
sudo install -m 0644 "$source_directory/platform/docker-compose.production.yml" /opt/sql-playzone/platform/docker-compose.yml
sudo install -m 0644 "$source_directory/platform/conf/nginx/http.conf" /opt/sql-playzone/platform/conf/nginx/http.conf
# Keep every public runtime image in the AMI so instance boot does not depend on Docker Hub.
sudo env CTFD_IMAGE="$ctfd_tag" SQL_JUDGE_IMAGE="$sql_judge_tag" \
  docker compose -f /opt/sql-playzone/platform/docker-compose.yml pull permissions nginx
sudo install -d -o ubuntu -g ubuntu /opt/sql-playzone/platform/.data/CTFd/logs /opt/sql-playzone/platform/.data/CTFd/uploads
sudo touch /opt/sql-playzone/platform/.env
sudo chown ubuntu:ubuntu /opt/sql-playzone/platform/.env
sudo chmod 0600 /opt/sql-playzone/platform/.env

sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/* /root/.cache /home/ubuntu/.cache
sudo cloud-init clean --logs
