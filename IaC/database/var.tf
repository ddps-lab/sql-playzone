variable "prefix" {
  description = "The prefix to use for all resources"
  type        = string
  default     = "CTFd"
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
    # 원래 private_subnet 도 사용하지만, 현재 상황에서는
    # private subnet 을 따로 사용하지 않을 것
    # data subnet 만 사용한다.
    # private subnet 과 data subnet 의 차이점은 NAT gateway
    # 의 존재 여부이다. private subnet => NAT gateway 존재
    # data subnet => NAT gateway 존재 x
    default     = ["192.168.20.0/24", "192.168.21.0/24"]
}

variable "data_subnet_cidrs" {
    description = "The CIDR blocks for the data subnets"
    type        = list(string)
    # RDS는 최소 2개의 서브넷이 다른 AZ에 있어야 함
    default     = ["192.168.30.0/24", "192.168.31.0/24"]
}

# RDS 관련 변수들
variable "engine_version" {
    description = "MariaDB engine version"
    type        = string
    default     = "10.11.4"
}

variable "instance_class" {
    description = "Instance class for RDS"
    type        = string
    default     = "db.t3.medium"
}