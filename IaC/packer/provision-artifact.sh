#!/usr/bin/env bash
set -euo pipefail

working_directory=$(mktemp -d)
buildx_builder="sql-playzone-${RELEASE_ID}"

cleanup() {
  sudo docker buildx rm "$buildx_builder" >/dev/null 2>&1 || true
  sudo rm -rf "$working_directory"
}
trap cleanup EXIT

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
ctfd_cache="$registry/$CTFD_CACHE_REPOSITORY_NAME:cache-${ARTIFACT_CHANNEL}"
sql_judge_cache="$registry/$SQL_JUDGE_CACHE_REPOSITORY_NAME:cache-${ARTIFACT_CHANNEL}"

aws ecr get-login-password --region "$AWS_REGION" | sudo docker login --username AWS --password-stdin "$registry"
sudo docker buildx create --name "$buildx_builder" --driver docker-container --use
sudo docker buildx inspect --bootstrap

build_image() {
  local name=$1
  local tag=$2
  local cache=$3
  local context=$4

  sudo docker buildx build \
    --builder "$buildx_builder" \
    --platform linux/arm64 \
    --pull \
    --cache-from "type=registry,ref=$cache" \
    --cache-to "type=registry,ref=$cache,mode=max,image-manifest=true,oci-mediatypes=true" \
    --tag "$tag" \
    --push \
    "$context" 2>&1 | sed -u "s/^/[$name] /"
}

build_image "ctfd" "$ctfd_tag" "$ctfd_cache" "$source_directory/platform" &
ctfd_pid=$!
build_image "sql-judge" "$sql_judge_tag" "$sql_judge_cache" "$source_directory/platform/CTFd/plugins/sql_challenges" &
sql_judge_pid=$!

build_failed=0
if ! wait "$ctfd_pid"; then
  build_failed=1
fi
if ! wait "$sql_judge_pid"; then
  build_failed=1
fi
if (( build_failed != 0 )); then
  echo "One or more image builds failed" >&2
  exit 1
fi

# Load only the immutable runtime images into Docker's image store before removing BuildKit cache.
sudo docker pull "$ctfd_tag"
sudo docker pull "$sql_judge_tag"

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

# Remove BuildKit's local cache and credentials while retaining the pulled runtime images.
sudo docker buildx rm "$buildx_builder"
sudo docker builder prune -af
sudo docker logout "$registry" || true
sudo rm -rf /root/.docker /root/.cache /home/ubuntu/.cache
sudo cloud-init clean --logs
sudo fstrim -av
df -h /
sudo docker images --format '{{.Repository}}@{{.Digest}} {{.Size}}'
