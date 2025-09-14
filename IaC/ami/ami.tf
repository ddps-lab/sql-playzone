resource "aws_ecr_repository" "platform-sql-judge-ecr-repository" {
  name                 = "platform-sql-judge"
  image_tag_mutability = "MUTABLE"
  force_delete         = true  # Allow deletion even with images

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_ecr_repository" "platform-sql-judge-ecr-ctfd" {
  name                 = "platform-ctfd"
  image_tag_mutability = "MUTABLE"
  force_delete         = true  # Allow deletion even with images

  image_scanning_configuration {
    scan_on_push = false
  }
}

# IAM Role for EC2 instance with ECR access
resource "aws_iam_role" "ami_builder_role" {
  name = "${var.prefix}-ami-builder-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.prefix}-ami-builder-role"
  }
}

# IAM Policy for ECR read/write access
resource "aws_iam_policy" "ecr_access_policy" {
  name        = "${var.prefix}-ecr-access-policy"
  description = "Policy for ECR read and write access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = "${var.prefix}-ecr-access-policy"
  }
}

# Attach ECR policy to the role
resource "aws_iam_role_policy_attachment" "ecr_policy_attachment" {
  role       = aws_iam_role.ami_builder_role.name
  policy_arn = aws_iam_policy.ecr_access_policy.arn
}

# Instance Profile for EC2
resource "aws_iam_instance_profile" "ami_builder_profile" {
  name = "${var.prefix}-ami-builder-profile"
  role = aws_iam_role.ami_builder_role.name

  tags = {
    Name = "${var.prefix}-ami-builder-profile"
  }
}

# Local variable to safely check AMI existence
locals {
  ami_exists_arm = try(length(data.aws_ami_ids.existing_ctfd_ami_arm.ids) > 0, false)
}

# AMI Builder Instance for ARM
resource "aws_instance" "ami_builder_arm" {
  count = local.ami_exists_arm ? 0 : 1  # Only create if AMI doesn't exist
  
  ami           = data.aws_ami.ubuntu_arm.id
  instance_type = "t4g.small"
  subnet_id     = var.public_subnet_ids[0]
  vpc_security_group_ids = [var.ec2_security_group_id]
  iam_instance_profile = aws_iam_instance_profile.ami_builder_profile.name

  depends_on = [ aws_ecr_repository.platform-sql-judge-ecr-repository, aws_ecr_repository.platform-sql-judge-ecr-ctfd ]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = base64encode(templatefile("${path.module}/ami-builder-userdata.sh", {
    DB_USERNAME  = var.db_username
    DB_PASSWORD  = var.db_password
    RDS_ENDPOINT = var.rds_endpoint
    CTFD_SECRET_KEY = var.ctfd_secret_key
    UPLOAD_FOLDER="/var/uploads"
    REDIS_URL="redis://cache:6379"
    WORKERS=1
    LOG_FOLDER="/var/log/CTFd"
    ACCESS_LOG="/var/log/CTFd/access.log"
    ERROR_LOG="/var/log/CTFd/error.log"
    REVERSE_PROXY=true
    SQL_JUDGE_SERVER_URL="http://sql-judge:8080"
    GOOGLE_CLIENT_ID = var.google_client_id
    GOOGLE_CLIENT_SECRET = var.google_client_secret
    REGION = var.region
    AWS_ACCOUNT_ID = var.aws_account_id
  }))

  tags = {
    Name = "${var.prefix}-ami-builder-arm"
  }
}

# Wait for AMI builders to complete
resource "time_sleep" "wait_for_build" {
  count = local.ami_exists_arm ? 0 : 1  # Only wait if building new AMI
  
  depends_on = [aws_instance.ami_builder_arm]
  create_duration = "6m"  # Docker build 시간 대기
}

# Create AMI from the ARM64 builder instance
resource "aws_ami_from_instance" "ctfd_ami_arm" {
  count = local.ami_exists_arm ? 0 : 1  # Only create if AMI doesn't exist
  
  name               = "${var.prefix}-ctfd-arm"
  source_instance_id = aws_instance.ami_builder_arm[0].id
  depends_on         = [time_sleep.wait_for_build]

  lifecycle {
    ignore_changes = [source_instance_id]
  }

  tags = {
    Name = "${var.prefix}-ctfd-ami-arm"
    Architecture = "arm"
    BuildDate = timestamp()
  }
}

# Terminate the ARM builder instance after AMI creation
resource "null_resource" "terminate_builder_arm" {
  count = local.ami_exists_arm ? 0 : 1  # Only run if we created a new AMI
  
  depends_on = [aws_ami_from_instance.ctfd_ami_arm]

  provisioner "local-exec" {
    command = "aws ec2 terminate-instances --instance-ids ${aws_instance.ami_builder_arm[0].id} --region ${var.region} --profile ${var.aws_profile}"
  }
}