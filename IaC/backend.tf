terraform {
  required_version = "~> 1.16.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.62.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.3.1"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14.1"
    }
  }

  backend "s3" {
    bucket       = "hyu-ddps-sql-playzone-tfstate-786382940258-ap-northeast-2"
    key          = "sql-playzone/prod/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
