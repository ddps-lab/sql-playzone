resource "aws_cloudwatch_log_group" "application" {
  name = local.application_log_group_name
}

resource "aws_cloudwatch_log_group" "behavior" {
  name              = local.behavior_log_group_name
  retention_in_days = 3
}

resource "aws_s3_bucket" "log_archive" {
  bucket        = local.log_bucket_name
  force_destroy = var.deployment_mode == "ephemeral"
}

resource "aws_s3_bucket_ownership_controls" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
