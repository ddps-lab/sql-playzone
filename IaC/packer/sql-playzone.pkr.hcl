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

variable "aws_account_id" {
  type = string
}

variable "artifact_prefix" {
  type    = string
  default = "sql-2026-s2"
}

variable "builder_instance_profile" {
  type = string
}

variable "builder_base_ami_id" {
  type = string
}

variable "artifact_channel" {
  type = string
}

variable "repository_url" {
  type    = string
  default = "https://github.com/ddps-lab/sql-playzone.git"
}

variable "commit_sha" {
  type = string
}

variable "release_id" {
  type = string
}

variable "ctfd_repository_name" {
  type = string
}

variable "ctfd_cache_repository_name" {
  type = string
}

variable "sql_judge_repository_name" {
  type = string
}

variable "sql_judge_cache_repository_name" {
  type = string
}

variable "manifest_output" {
  type = string
}

source "amazon-ebs" "sql_playzone" {
  ami_description = "SQL Playzone ${var.release_id}"
  ami_name        = "${var.artifact_prefix}-${var.release_id}"

  associate_public_ip_address = true
  iam_instance_profile        = var.builder_instance_profile
  instance_type               = "c7g.xlarge"
  profile                     = var.aws_profile
  region                      = var.region
  source_ami                  = var.builder_base_ami_id
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
    Name            = "${var.artifact_prefix}-packer-${var.release_id}"
    Project         = "sql-playzone"
    ArtifactRelease = var.release_id
    ManagedBy       = "packer"
  }

  tags = {
    Name            = "${var.artifact_prefix}-${var.release_id}"
    Project         = "sql-playzone"
    ArtifactPrefix  = var.artifact_prefix
    ArtifactRelease = var.release_id
    CommitSha       = var.commit_sha
    ManagedBy       = "packer"
  }
}

build {
  name    = "sql-playzone"
  sources = ["source.amazon-ebs.sql_playzone"]

  provisioner "shell" {
    environment_vars = [
      "ARTIFACT_PREFIX=${var.artifact_prefix}",
      "ARTIFACT_CHANNEL=${var.artifact_channel}",
      "AWS_ACCOUNT_ID=${var.aws_account_id}",
      "AWS_REGION=${var.region}",
      "COMMIT_SHA=${var.commit_sha}",
      "CTFD_REPOSITORY_NAME=${var.ctfd_repository_name}",
      "CTFD_CACHE_REPOSITORY_NAME=${var.ctfd_cache_repository_name}",
      "RELEASE_ID=${var.release_id}",
      "REPOSITORY_URL=${var.repository_url}",
      "SQL_JUDGE_REPOSITORY_NAME=${var.sql_judge_repository_name}",
      "SQL_JUDGE_CACHE_REPOSITORY_NAME=${var.sql_judge_cache_repository_name}"
    ]
    script = "${path.root}/provision-artifact.sh"
  }

  post-processor "manifest" {
    custom_data = {
      artifact_prefix = var.artifact_prefix
      base_ami_id     = var.builder_base_ami_id
      commit_sha      = var.commit_sha
      release_id      = var.release_id
    }
    output     = var.manifest_output
    strip_path = true
  }
}
