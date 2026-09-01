provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project    = "sql-playzone"
      Deployment = var.prefix
      ManagedBy  = "terraform"
    }
  }
}

# VPC Module
module "vpc" {
  source = "./vpc"

  vpc_name             = "${var.prefix}-vpc"
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  data_subnet_cidrs    = var.data_subnet_cidrs
}

# RDS Module (Aurora Serverless v2)
module "rds" {
  source = "./rds"

  rds_name                = "${var.prefix}-rds"
  vpc_id                  = module.vpc.vpc.id
  data_subnet_ids         = module.vpc.data_subnet_ids
  rds_security_group_id   = module.vpc.rds_security_group_id
  db_username             = var.db_username
  aurora_engine_version   = var.aurora_engine_version
  aurora_min_capacity     = var.aurora_min_capacity
  aurora_max_capacity     = var.aurora_max_capacity
  aurora_instance_count   = var.aurora_instance_count
  deletion_protection     = var.deployment_mode == "persistent"

  depends_on = [module.vpc]
}

# ElastiCache Module
module "elasticache" {
  source = "./elasticache"

  prefix                     = var.prefix
  elasticache_security_group_id = module.vpc.elasticache_security_group_id
  data_subnet_ids            = module.vpc.data_subnet_ids

  depends_on = [module.vpc]
}

# EC2 Module
module "ec2" {
  source = "./ec2"

  prefix                          = var.prefix
  vpc_id                          = module.vpc.vpc.id
  public_subnet_ids               = module.vpc.public_subnet_ids
  alb_security_group_id           = module.vpc.alb_security_group_id
  ec2_security_group_id           = module.vpc.ec2_security_group_id
  hosted_zone_id                  = var.hosted_zone_id
  domain_name                     = var.domain_name
  on_demand_base_capacity         = var.on_demand_base_capacity
  on_demand_percentage_above_base = var.on_demand_percentage_above_base
  asg_min_size                    = var.asg_min_size
  asg_max_size                    = var.asg_max_size
  asg_desired_capacity            = var.asg_desired_capacity
  key_name                        = var.ssh_key_name
  ondemand_instance_type          = var.ondemand_server_instance_class
  region                          = var.region
  aws_account_id                  = var.aws_account_id
  artifact_prefix                 = var.artifact_prefix
  artifact_channel                = var.artifact_channel
  artifact_release_id             = local.selected_release_id
  ami_id                          = local.release_manifest.ami_id
  ctfd_image                      = local.release_manifest.ctfd_image
  sql_judge_image                 = local.release_manifest.sql_judge_image
  application_log_group_name      = aws_cloudwatch_log_group.application.name
  behavior_log_group_name         = aws_cloudwatch_log_group.behavior.name
  behavior_log_stream_name        = local.behavior_log_stream_name
  application_secret_name         = local.application_secret_name
  rds_master_secret_arn           = module.rds.master_user_secret_arn
  rds_endpoint                    = module.rds.rds_endpoint
  elasticache_serverless_endpoint = module.elasticache.elasticache_serverless_endpoint[0].address

  depends_on = [module.vpc, module.rds]
}

# Lambda Module
module "lambda" {
  source = "./lambda"

  prefix         = var.prefix
  region         = var.region
  aws_account_id = var.aws_account_id
  bucket_name     = aws_s3_bucket.log_archive.bucket
  log_group_name  = aws_cloudwatch_log_group.behavior.name
  log_stream_name = local.behavior_log_stream_name

  depends_on = [module.vpc]
}
