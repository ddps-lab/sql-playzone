# VPC Configuration
resource "aws_vpc" "vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.vpc_name}"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "${var.vpc_name}-igw"
  }
}

# Public Subnets
resource "aws_subnet" "public_subnets" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.vpc_name}-public-subnet-${count.index + 1}"
  }
}

# Private Subnets
resource "aws_subnet" "private_subnets" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.vpc_name}-private-subnet-${count.index + 1}"
  }
}

# Data Subnets for RDS (NAT gateway 없음)
resource "aws_subnet" "data_subnets" {
  count             = length(var.data_subnet_cidrs)
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = var.data_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.vpc_name}-data-subnet-${count.index + 1}"
  }
}

# Route Table for Public Subnets (1 for all public subnets)
resource "aws_route_table" "public_subnet_route_table" {
  vpc_id = aws_vpc.vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "${var.vpc_name}-public-subnet-route-table"
  }
}

# Associate Route Table with Public Subnets
resource "aws_route_table_association" "public_subnet_table_association" {
  count          = length(aws_subnet.public_subnets)
  subnet_id      = aws_subnet.public_subnets[count.index].id
  route_table_id = aws_route_table.public_subnet_route_table.id
}


# Elastic IP for NAT Gateway 
resource "aws_eip" "nat_gateway_eip" {
  count  = length(var.private_subnet_cidrs)
  domain = "vpc"

  tags = {
    Name = "${var.vpc_name}-nat-eip-${count.index + 1}"
  }
}

# NAT Gateway 
# public subnet 에 생성되며,
# public subnet 보다 private subnet 의 개수가
# 같거나 더 적다고 가정함.
resource "aws_nat_gateway" "nat_gateway" {
  count         = length(var.private_subnet_cidrs)
  allocation_id = aws_eip.nat_gateway_eip[count.index].id
  subnet_id     = aws_subnet.public_subnets[count.index].id

  tags = {
    Name = "${var.vpc_name}-nat-gateway-${count.index + 1}"
  }
}

# Private route tables
resource "aws_route_table" "private_route_tables" {
  vpc_id = aws_vpc.vpc.id
  count = length(var.private_subnet_cidrs)

  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_gateway[count.index].id
  }

  tags = {
    "Name" : "${var.vpc_name}-private-route-table-${data.aws_availability_zones.available.names[count.index]}"
  }
}

# Security Group for ALB
resource "aws_security_group" "alb_sg" {
  name        = "${var.vpc_name}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.vpc_name}-alb-sg"
  }
}

# Security Group for EC2 instances
resource "aws_security_group" "ec2_sg" {
  name        = "${var.vpc_name}-ec2-sg"
  description = "Security group for EC2 instances"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.vpc_name}-ec2-sg"
  }
}

# Security Group for RDS
resource "aws_security_group" "rds_sg" {
  name        = "${var.vpc_name}-rds-sg"
  description = "Security group for RDS instance"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.vpc_name}-rds-sg"
  }
}