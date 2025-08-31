# DB Subnet Group
resource "aws_db_subnet_group" "rds_subnet_group" {
  name       = "${var.rds_name}-subnet-group"
  subnet_ids = var.data_subnet_ids

  tags = {
    Name = "${var.rds_name}-subnet-group"
  }
}

# Security Group for RDS
resource "aws_security_group" "rds_sg" {
  name        = "${var.rds_name}-sg"
  description = "Security group for RDS instance"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.rds_name}-sg"
  }
}

# Security Group Rule - Allow from same security group
resource "aws_security_group_rule" "rds_sg_ingress" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.rds_sg.id
  security_group_id        = aws_security_group.rds_sg.id
}

# RDS Instance
resource "aws_db_instance" "rds" {
  identifier     = var.rds_name
  engine         = "mariadb"
  engine_version = var.engine_version

  instance_class        = var.instance_class
  allocated_storage     = 30
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  username = var.db_username
  password = var.db_password

  multi_az               = false
  publicly_accessible    = false
  backup_retention_period = 7  # 7일간 백업 보관
  backup_window          = "03:00-04:00"  # 새벽 3-4시에 백업
  maintenance_window     = "sun:04:00-sun:05:00"

  skip_final_snapshot = true
  deletion_protection = true

  tags = {
    Name = var.rds_name
  }
}