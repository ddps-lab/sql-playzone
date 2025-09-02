provider "aws" {
  region  = var.region
  profile = var.aws_profile
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

  rds_name                = "${var.prefix}-rds"
  vpc_id                  = module.vpc.vpc.id
  data_subnet_ids         = module.vpc.data_subnet_ids
  rds_security_group_id   = module.vpc.rds_security_group_id
  db_username             = var.db_username
  db_password             = var.db_password
  engine_version          = var.engine_version
  database_instance_class = var.database_instance_class

  depends_on = [module.vpc]
}

# AMI Module
module "ami" {
  source = "./ami"

  prefix                = var.prefix
  region                = var.region
  aws_profile           = var.aws_profile
  public_subnet_ids     = module.vpc.public_subnet_ids
  ec2_security_group_id = module.vpc.ec2_security_group_id
  rds_endpoint          = module.rds.rds_endpoint
  db_username           = var.db_username
  db_password           = var.db_password
  ctfd_secret_key       = var.ctfd_secret_key
  google_client_id      = var.google_client_id
  google_client_secret  = var.google_client_secret

  depends_on = [module.vpc, module.rds]
}

# EC2 Module
module "ec2" {
  source = "./ec2"

  prefix                           = var.prefix
  vpc_id                           = module.vpc.vpc.id
  public_subnet_ids                = module.vpc.public_subnet_ids
  alb_security_group_id            = module.vpc.alb_security_group_id
  ec2_security_group_id            = module.vpc.ec2_security_group_id
  hosted_zone_id                   = var.hosted_zone_id
  domain_name                      = var.domain_name
  on_demand_base_capacity          = var.on_demand_base_capacity
  on_demand_percentage_above_base  = var.on_demand_percentage_above_base
  asg_min_size                     = var.asg_min_size
  asg_max_size                     = var.asg_max_size
  asg_desired_capacity             = var.asg_desired_capacity
  key_name                         = var.ssh_key_name
  ondemand_instance_type           = var.ondemand_server_instance_class
  ctfd_ami_arm_id                  = module.ami.ctfd_ami_arm_id

  depends_on = [module.vpc, module.rds, module.ami]
}

