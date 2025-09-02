data "aws_route53_zone" "route53_zone" {
  zone_id = var.hosted_zone_id
}