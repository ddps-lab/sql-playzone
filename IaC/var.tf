variable "prefix" {
  description = "The prefix to use for all resources"
  type        = string
  default     = "playzone"
}

variable "aws_profile" {
  description = "AWS CLI profile used by local provisioner commands"
  type        = string
  default     = "hyu-ddps"
}

variable "aws_account_id" {
  description = "AWS account ID where SQL Playzone is deployed"
  type        = string
}

variable "db_username" {
  description = "Aurora master username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Aurora master password"
  type        = string
  sensitive   = true
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
}

variable "ssh_key_name" {
  description = "EC2 key pair name"
  type        = string
}

variable "ctfd_secret_key" {
  description = "CTFd session signing secret"
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "vpc_cidr" {
  description = "The CIDR block for the VPC"
  type        = string
  default     = "192.168.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "The CIDR blocks for the public subnets"
  type        = list(string)
  default     = ["192.168.10.0/24", "192.168.11.0/24"]
}

variable "private_subnet_cidrs" {
  description = "The CIDR blocks for the private subnets"
  type        = list(string)
  # default     = ["192.168.20.0/24", "192.168.21.0/24"]
  default = []
  # 원래 private_subnet 도 사용하지만, 현재 상황에서는
  # private subnet 을 따로 사용하지 않을 것
  # data subnet 만 사용한다.
  # private subnet 과 data subnet 의 차이점은 NAT gateway
  # 의 존재 여부이다. private subnet => NAT gateway 존재
  # data subnet => NAT gateway 존재 x
}

variable "data_subnet_cidrs" {
  description = "The CIDR blocks for the data subnets"
  type        = list(string)
  # RDS는 최소 2개의 서브넷이 다른 AZ에 있어야 함
  default = ["192.168.30.0/24", "192.168.31.0/24"]
}

# Aurora Serverless v2 관련 변수들
variable "aurora_engine_version" {
  description = "Aurora MySQL engine version"
  type        = string
  default     = "8.0.mysql_aurora.3.08.2" # Aurora MySQL 8.0 compatible
}

variable "aurora_min_capacity" {
  description = "Minimum capacity for Aurora Serverless v2 (in ACUs)"
  type        = number
  default     = 0.5 # 최소 0.5 ACU
}

variable "aurora_max_capacity" {
  description = "Maximum capacity for Aurora Serverless v2 (in ACUs)"
  type        = number
  default     = 32 # 최대 32 ACU
}

variable "aurora_instance_count" {
  description = "Number of Aurora instances"
  type        = number
  default     = 1 # 기본 1개 인스턴스 (writer)
}

# # 기존 RDS 변수들 (마이그레이션 후 제거 예정)
# variable "engine_version" {
#   description = "MariaDB engine version"
#   type        = string
#   default     = "10.11.14"
# }

# variable "database_instance_class" {
#   description = "Instance class for RDS"
#   type        = string
#   default     = "db.t3.medium"
# }

variable "ondemand_server_instance_class" {
  type    = string
  default = "t4g.small"
}

# EC2 관련 변수들
variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "playzone.ddps.cloud"
}

variable "on_demand_base_capacity" {
  description = "Base on-demand instance capacity"
  type        = number
  default     = 1
}

variable "on_demand_percentage_above_base" {
  description = "Percentage of on-demand instances above base capacity"
  type        = number
  default     = 0
}

variable "asg_min_size" {
  description = "Minimum size of Auto Scaling Group"
  type        = number
  default     = 1
}

variable "asg_max_size" {
  description = "Maximum size of Auto Scaling Group"
  type        = number
  default     = 10
}

variable "asg_desired_capacity" {
  description = "Desired capacity of Auto Scaling Group"
  type        = number
  default     = 1
}

variable "log_bucket_name" {
  description = "S3 Bucket name for storing logs"
  type        = string
  default     = "sql-playzone-log"
}

variable "behavior_log_group_name" {
  description = "CloudWatch Log Group name for behavior logs"
  type        = string
  default     = "/aws/ec2/sql-playzone-behavior"
}

variable "behavior_log_stream_name" {
  description = "CloudWatch Log Stream name for behavior logs"
  type        = string
  default     = "sql-challenge"
}
