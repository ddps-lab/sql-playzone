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