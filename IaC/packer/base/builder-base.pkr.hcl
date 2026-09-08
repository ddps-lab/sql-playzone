packer {
  required_version = "~> 1.16.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "= 1.8.2"
    }
  }
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "aws_profile" {
  type    = string
  default = "hyu-ddps"
}

variable "artifact_prefix" {
  type    = string
  default = "sql-2026-s2"
}

variable "builder_instance_profile" {
  type = string
}

variable "base_id" {
  type = string
}

variable "manifest_output" {
  type = string
}

data "amazon-ami" "ubuntu_arm" {
  filters = {
    name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"
    root-device-type    = "ebs"
    virtualization-type = "hvm"
  }
  most_recent = true
  owners      = ["099720109477"]
  profile     = var.aws_profile
  region      = var.region
}

source "amazon-ebs" "builder_base" {
  ami_description = "SQL Playzone artifact builder base ${var.base_id}"
  ami_name        = "${var.artifact_prefix}-builder-base-${var.base_id}"

  associate_public_ip_address = true
  iam_instance_profile        = var.builder_instance_profile
  instance_type               = "t4g.small"
  profile                     = var.aws_profile
  region                      = var.region
  source_ami                  = data.amazon-ami.ubuntu_arm.id
  ssh_timeout                 = "15m"
  ssh_username                = "ubuntu"

  temporary_security_group_source_public_ip = true

  vpc_filter {
    filters = {
      "is-default" = "true"
    }
  }

  subnet_filter {
    filters = {
      "map-public-ip-on-launch" = "true"
    }
    most_free = true
  }

  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    delete_on_termination = true
    encrypted             = true
    volume_size           = 16
    volume_type           = "gp3"
  }

  run_tags = {
    Name           = "${var.artifact_prefix}-packer-builder-base-${var.base_id}"
    Project        = "sql-playzone"
    ArtifactPrefix = var.artifact_prefix
    ArtifactRole   = "builder-base"
    ManagedBy      = "packer"
  }

  tags = {
    Name           = "${var.artifact_prefix}-builder-base-${var.base_id}"
    Project        = "sql-playzone"
    ArtifactPrefix = var.artifact_prefix
    ArtifactRole   = "builder-base"
    ManagedBy      = "packer"
  }
}

build {
  name    = "builder-base"
  sources = ["source.amazon-ebs.builder_base"]

  provisioner "shell" {
    script = "${path.root}/provision-builder-base.sh"
  }

  post-processor "manifest" {
    custom_data = {
      artifact_prefix    = var.artifact_prefix
      ubuntu_base_ami_id = data.amazon-ami.ubuntu_arm.id
    }
    output     = var.manifest_output
    strip_path = true
  }
}
