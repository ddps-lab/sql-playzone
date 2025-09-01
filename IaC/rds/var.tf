variable "rds_name" { type = string }
variable "vpc_id" { type = string }
variable "data_subnet_ids" { type = list(string) }
variable "rds_security_group_id" { type = string }
variable "db_username" { type = string }
variable "db_password" { type = string }
variable "engine_version" { type = string }
variable "database_instance_class" { type = string }
