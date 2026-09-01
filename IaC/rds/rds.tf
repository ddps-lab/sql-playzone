# DB Subnet Group
resource "aws_db_subnet_group" "aurora_subnet_group" {
  name       = "${var.rds_name}-aurora-serverless-subnet-group"
  subnet_ids = var.data_subnet_ids

  tags = {
    Name = "${var.rds_name}-aurora-serverless-subnet-group"
  }
}

# Aurora Serverless v2 Cluster
resource "aws_rds_cluster" "aurora_serverless" {
  cluster_identifier = "${var.rds_name}-aurora-serverless-cluster"
  
  engine         = "aurora-mysql"
  engine_version = var.aurora_engine_version
  
  database_name   = "ctfd"
  master_username = var.db_username
  manage_master_user_password = true
  
  db_subnet_group_name   = aws_db_subnet_group.aurora_subnet_group.name
  vpc_security_group_ids = [var.rds_security_group_id]
  
  # Serverless v2 scaling configuration
  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }
  
  # Backup configuration
  backup_retention_period = 1
  preferred_backup_window = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"
  
  # Security - 암호화 활성화 (AWS managed key 사용)
  storage_encrypted = true
  
  # Deletion protection
  deletion_protection = true
  skip_final_snapshot = true
  
  tags = {
    Name = "${var.rds_name}-aurora-serverless-cluster"
    Type = "Aurora Serverless v2"
  }
}

# Aurora Serverless v2 Instance (필수 - 최소 1개 필요)
resource "aws_rds_cluster_instance" "aurora_instance" {
  count = var.aurora_instance_count
  
  identifier         = "${var.rds_name}-aurora-serverless-instance-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.aurora_serverless.id
  
  instance_class = "db.serverless"
  engine         = aws_rds_cluster.aurora_serverless.engine
  engine_version = aws_rds_cluster.aurora_serverless.engine_version
  
  performance_insights_enabled = false
  
  tags = {
    Name = "${var.rds_name}-aurora-serverless-instance-${count.index + 1}"
  }
}
