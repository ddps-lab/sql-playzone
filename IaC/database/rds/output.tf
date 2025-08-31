output "rds_endpoint" {
  value = aws_db_instance.rds.endpoint
}

output "rds_security_group_name" {
  value = aws_security_group.rds_sg.name
}