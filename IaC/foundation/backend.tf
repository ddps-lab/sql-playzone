terraform {
  required_version = "~> 1.16.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.62"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project    = "sql-playzone"
      Deployment = var.artifact_prefix
      ManagedBy  = "terraform"
      Lifecycle  = "semester"
    }
  }
}
