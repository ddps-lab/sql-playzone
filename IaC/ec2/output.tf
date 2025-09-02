output "server_domain_name" {
  value = aws_route53_record.dns_record.name
}