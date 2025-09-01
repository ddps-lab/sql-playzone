output "vpc" {
  value = aws_vpc.vpc
}

output "public_subnet_ids" {
  value = tolist(aws_subnet.public_subnets[*].id)
}

output "private_subnet_ids" {
  value = tolist(aws_subnet.private_subnets[*].id)
}

output "data_subnet_ids" {
  value = tolist(aws_subnet.data_subnets[*].id)
}

output "alb_security_group_id" {
  value = aws_security_group.alb_sg.id
}

output "ec2_security_group_id" {
  value = aws_security_group.ec2_sg.id
}

output "rds_security_group_id" {
  value = aws_security_group.rds_sg.id
}