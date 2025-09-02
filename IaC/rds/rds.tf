# DB Subnet Group
resource "aws_db_subnet_group" "rds_subnet_group" {
  name       = "${var.rds_name}-subnet-group"
  subnet_ids = var.data_subnet_ids

  tags = {
    Name = "${var.rds_name}-subnet-group"
  }
}

# RDS Instance
resource "aws_db_instance" "rds" {
  identifier     = var.rds_name
  engine         = "mariadb"
  engine_version = var.engine_version

  instance_class        = var.database_instance_class
  allocated_storage     = 30
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids = [var.rds_security_group_id]

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