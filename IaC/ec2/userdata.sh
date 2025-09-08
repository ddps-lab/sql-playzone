#!/bin/bash
cd /home/ubuntu/sql-playzone/platform

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