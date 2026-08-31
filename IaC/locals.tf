locals {
  ctfd_ecr_repository_name      = "${var.prefix}-ctfd"
  sql_judge_ecr_repository_name = "${var.prefix}-sql-judge"

  application_log_group_name = "/aws/ec2/${var.prefix}"
  behavior_log_group_name    = "/aws/ec2/${var.prefix}-behavior"
  behavior_log_stream_name   = "${var.prefix}-sql-challenge"
  log_bucket_name            = "${var.prefix}-logs-${var.aws_account_id}-${var.region}"
}
