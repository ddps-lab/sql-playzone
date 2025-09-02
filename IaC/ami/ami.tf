# AMI Builder Instance for ARM
resource "aws_instance" "ami_builder_arm" {
  ami           = data.aws_ami.ubuntu_arm.id
  instance_type = "t4g.small"
  subnet_id     = var.public_subnet_ids[0]
  vpc_security_group_ids = [var.ec2_security_group_id]

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
    ACCESS_LOG="/var/log/CTFd-access"
    ERROR_LOG="/var/log/CTFd-error"
    REVERSE_PROXY=true
    SQL_JUDGE_SERVER_URL="http://sql-judge:8080"
    GOOGLE_CLIENT_ID = var.google_client_id
    GOOGLE_CLIENT_SECRET = var.google_client_secret
  }))

  tags = {
    Name = "${var.prefix}-ami-builder-arm"
  }
}

# Wait for AMI builders to complete
resource "time_sleep" "wait_for_build" {
  # depends_on = [aws_instance.ami_builder_amd, aws_instance.ami_builder_arm]
  depends_on = [aws_instance.ami_builder_arm]
  create_duration = "6m"  # Docker build 시간 대기
}

# Create AMI from the ARM64 builder instance
resource "aws_ami_from_instance" "ctfd_ami_arm" {
  name               = "${var.prefix}-ctfd-arm-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
  source_instance_id = aws_instance.ami_builder_arm.id
  depends_on         = [time_sleep.wait_for_build]

  tags = {
    Name = "${var.prefix}-ctfd-ami-arm"
    Architecture = "arm"
    BuildDate = timestamp()
  }
}

# Terminate the ARM builder instance after AMI creation
resource "null_resource" "terminate_builder_arm" {
  depends_on = [aws_ami_from_instance.ctfd_ami_arm]

  provisioner "local-exec" {
    command = "aws ec2 terminate-instances --instance-ids ${aws_instance.ami_builder_arm.id} --region ${var.region} --profile ${var.aws_profile}"
  }
}