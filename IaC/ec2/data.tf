data "aws_route53_zone" "route53_zone" {
  zone_id = var.hosted_zone_id
}

# Find the CTFd AMI - must exist for EC2 module to work
data "aws_ami" "ctfd_ami_arm" {
  most_recent = true
  owners      = ["self"]

  filter {
    name   = "name"
    values = ["${var.prefix}-ctfd-arm"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}