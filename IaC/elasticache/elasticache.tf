resource "aws_elasticache_serverless_cache" "elasticache_serverless" {
    engine = "valkey"
    name = "${var.prefix}-elasticache-serverless"
    description = "ElastiCache Serverless for ${var.prefix}"
    security_group_ids = [var.elasticache_security_group_id]
    subnet_ids = var.data_subnet_ids
}