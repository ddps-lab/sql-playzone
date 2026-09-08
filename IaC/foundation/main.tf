locals {
  ctfd_repository_name      = "${var.artifact_prefix}-ctfd"
  sql_judge_repository_name = "${var.artifact_prefix}-sql-judge"
  build_cache_repositories = {
    ctfd      = "${var.artifact_prefix}-ctfd-cache"
    sql_judge = "${var.artifact_prefix}-sql-judge-cache"
  }
}

resource "aws_ecr_repository" "ctfd" {
  name                 = local.ctfd_repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "sql_judge" {
  name                 = local.sql_judge_repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "build_cache" {
  for_each = local.build_cache_repositories

  name                 = each.value
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_iam_role" "packer_builder" {
  name = "${var.artifact_prefix}-packer-builder-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "packer_builder_ecr" {
  name = "${var.artifact_prefix}-packer-builder-ecr"
  role = aws_iam_role.packer_builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeImages",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart"
        ]
        Resource = [
          aws_ecr_repository.ctfd.arn,
          aws_ecr_repository.sql_judge.arn,
          aws_ecr_repository.build_cache["ctfd"].arn,
          aws_ecr_repository.build_cache["sql_judge"].arn
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "packer_builder" {
  name = "${var.artifact_prefix}-packer-builder-profile"
  role = aws_iam_role.packer_builder.name
}
