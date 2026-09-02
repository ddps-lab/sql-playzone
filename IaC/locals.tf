locals {
  artifact_namespace      = "/sql-playzone/${var.artifact_prefix}"
  application_secret_name = "sql-playzone/${var.prefix}/application"

  application_log_group_name = "/aws/ec2/${var.prefix}"
  behavior_log_group_name    = "/aws/ec2/${var.prefix}-behavior"
  behavior_log_stream_name   = "${var.prefix}-sql-challenge"
  log_bucket_name            = "${var.prefix}-logs-${var.aws_account_id}-${var.region}"
  upload_bucket_name         = "${var.prefix}-uploads-${var.aws_account_id}-${var.region}"
}
