# CTFd uploads (challenge attachments and other files) live in S3 rather than
# on the instance root volume. Instances are replaced by every release
# (instance refresh) and run behind an ASG, so local uploads would be lost on
# each deployment and invisible to other instances.
resource "aws_s3_bucket" "uploads" {
  bucket        = local.upload_bucket_name
  force_destroy = var.deployment_mode == "ephemeral"
}

resource "aws_s3_bucket_ownership_controls" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
