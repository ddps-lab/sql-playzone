provider "aws" {
  region = var.region
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

# RDS Module
module "rds" {
  source = "./rds"
  
  rds_name        = "${var.prefix}-rds"
  vpc_id          = module.vpc.vpc.id
  data_subnet_ids = module.vpc.data_subnet_ids
  db_username     = private_var.db_username
  db_password     = private_var.db_password
  engine_version  = var.engine_version
  instance_class  = var.instance_class
  
  depends_on = [module.vpc]
}