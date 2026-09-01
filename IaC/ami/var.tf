variable "prefix" { type = string }
variable "region" { type = string }
variable "aws_profile" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "ec2_security_group_id" { type = string }
variable "aws_account_id" { type = string }
variable "ctfd_ecr_repository_name" { type = string }
variable "sql_judge_ecr_repository_name" { type = string }
