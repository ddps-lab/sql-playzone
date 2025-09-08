output "rds_endpoint" {
  value = aws_rds_cluster.aurora_serverless.endpoint
  description = "Aurora cluster writer endpoint"
}

output "rds_reader_endpoint" {
  value = aws_rds_cluster.aurora_serverless.reader_endpoint
  description = "Aurora cluster reader endpoint"
}

output "rds_port" {
  value = aws_rds_cluster.aurora_serverless.port
  description = "Aurora cluster port"
}