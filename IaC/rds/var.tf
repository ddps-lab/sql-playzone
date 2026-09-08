variable "rds_name" { type = string }
variable "vpc_id" { type = string }
variable "data_subnet_ids" { type = list(string) }
variable "rds_security_group_id" { type = string }
variable "db_username" { type = string }

# Aurora Serverless v2 관련 변수
variable "aurora_engine_version" { type = string }
variable "aurora_min_capacity" { type = number }
variable "aurora_max_capacity" { type = number }
variable "aurora_instance_count" { type = number }
variable "deletion_protection" { type = bool }
