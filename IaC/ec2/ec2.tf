# ACM Certificate for HTTPS
resource "aws_acm_certificate" "cert" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.prefix}-cert"
  }
}

# Route53 Records for Certificate DNS Validation
resource "aws_route53_record" "cert_validation_record" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = var.hosted_zone_id
}

# Certificate Validation
resource "aws_acm_certificate_validation" "cert_validation" {
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation_record : record.fqdn]
}

# Application Load Balancer
resource "aws_lb" "alb" {
  name               = "${var.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = false
  enable_http2              = true

  tags = {
    Name = "${var.prefix}-alb"
  }
}

# Target Group
resource "aws_lb_target_group" "tg" {
  name     = "${var.prefix}-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200,301,302"
  }

  deregistration_delay = 30

  tags = {
    Name = "${var.prefix}-tg"
  }
}

# HTTP Listener - Redirect to HTTPS
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS Listener
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.cert_validation.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }

  depends_on = [aws_acm_certificate_validation.cert_validation]
}

# Launch Template for ARM instances
resource "aws_launch_template" "arm_launch_template" {
  name_prefix   = "${var.prefix}-lt-arm"
  image_id      = var.ctfd_ami_arm_id
  instance_type = "t4g.micro"
  key_name      = var.key_name != "" ? var.key_name : null

  vpc_security_group_ids = [var.ec2_security_group_id]

  block_device_mappings {
    device_name = "/dev/sda1"
    
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/userdata.sh", {}))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.prefix}-instance-arm"
    }
  }
}

# Auto Scaling Group
resource "aws_autoscaling_group" "asg" {
  name                = "${var.prefix}-asg"
  vpc_zone_identifier = var.public_subnet_ids
  target_group_arns   = [aws_lb_target_group.tg.arn]
  
  min_size         = var.asg_min_size
  max_size         = var.asg_max_size
  desired_capacity = var.asg_desired_capacity

  health_check_type         = "ELB"
  health_check_grace_period = 120

  mixed_instances_policy {
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.arm_launch_template.id
        version            = "$Latest"
      }

      # First override - will be used for on-demand base capacity
      override {
        instance_type = var.ondemand_instance_type
      }

      # Additional overrides - will be used for spot instances
      override {
        instance_type = "t4g.medium"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm_launch_template.id
          version            = "$Latest"
        }
      }
      override {
        instance_type = "t4g.large"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm_launch_template.id
          version            = "$Latest"
        }
      }
    }

    instances_distribution {
      on_demand_base_capacity                  = var.on_demand_base_capacity
      on_demand_percentage_above_base_capacity = var.on_demand_percentage_above_base  # Scaling 시 on-demand 비율 (0이면 전부 spot)
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.prefix}-server"
    propagate_at_launch = true
  }
}

# Route53 Record
resource "aws_route53_record" "dns_record" {
  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.alb.dns_name
    zone_id                = aws_lb.alb.zone_id
    evaluate_target_health = true
  }
}

# Auto Scaling Policy - Request Count Per Target
resource "aws_autoscaling_policy" "request_count_tracking" {
  name                   = "${var.prefix}-request-count-tracking"
  autoscaling_group_name = aws_autoscaling_group.asg.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.alb.arn_suffix}/${aws_lb_target_group.tg.arn_suffix}"
    }
    target_value = 300.0  # 인스턴스당 300 요청 유지
  }
}