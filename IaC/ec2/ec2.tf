# Application Load Balancer

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

# ALB Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
}

# Launch Template for x86 instances
resource "aws_launch_template" "amd64" {
  name_prefix   = "${var.prefix}-lt"
  image_id      = data.aws_ami.ubuntu_amd.id
  instance_type = var.ondemand_instance_type
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

  user_data = base64encode(templatefile("${path.module}/userdata.sh", {
    DB_USERNAME  = var.db_username
    DB_PASSWORD  = var.db_password
    RDS_ENDPOINT = var.rds_endpoint
    UPLOAD_FOLDER="/var/uploads"
    REDIS_URL="redis://cache:6379"
    WORKERS=2
    LOG_FOLDER="/var/log/CTFd"
    ACCESS_LOG="/var/log/CTFd-access"
    ERROR_LOG="/var/log/CTFd-error"
    REVERSE_PROXY=true
    SQL_JUDGE_SERVER_URL="http://sql-judge:8080"
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.prefix}-instance"
    }
  }
}

# Launch Template for ARM instances
resource "aws_launch_template" "arm64" {
  name_prefix   = "${var.prefix}-lt-arm"
  image_id      = data.aws_ami.ubuntu_arm.id
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

  user_data = base64encode(templatefile("${path.module}/userdata.sh", {
    DB_USERNAME  = var.db_username
    DB_PASSWORD  = var.db_password
    RDS_ENDPOINT = var.rds_endpoint
    UPLOAD_FOLDER="/var/uploads"
    REDIS_URL="redis://cache:6379"
    WORKERS=2
    LOG_FOLDER="/var/log/CTFd"
    ACCESS_LOG="/var/log/CTFd-access"
    ERROR_LOG="/var/log/CTFd-error"
    REVERSE_PROXY=true
    SQL_JUDGE_SERVER_URL="http://sql-judge:8080"
  }))

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
  vpc_zone_identifier = var.private_subnet_ids
  target_group_arns   = [aws_lb_target_group.tg.arn]
  
  min_size         = var.asg_min_size
  max_size         = var.asg_max_size
  desired_capacity = var.asg_desired_capacity

  health_check_type         = "ELB"
  health_check_grace_period = 300

  mixed_instances_policy {
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.amd64.id
        version            = "$Latest"
      }

      # First override - will be used for on-demand base capacity
      override {
        instance_type = var.ondemand_instance_type
      }

      # Additional overrides - will be used for spot instances
      override {
        instance_type = "t3.micro"
      }
      override {
        instance_type = "t3.medium"
      }
      override {
        instance_type = "t3.large"
      }
      override {
        instance_type = "t4g.micro"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm64.id
          version            = "$Latest"
        }
      }
      override {
        instance_type = "t4g.small"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm64.id
          version            = "$Latest"
        }
      }
      override {
        instance_type = "t4g.medium"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm64.id
          version            = "$Latest"
        }
      }
      override {
        instance_type = "t4g.large"
        launch_template_specification {
          launch_template_id = aws_launch_template.arm64.id
          version            = "$Latest"
        }
      }
    }

    instances_distribution {
      on_demand_base_capacity                  = var.on_demand_base_capacity
      on_demand_percentage_above_base_capacity = 0  # Scaling 시 on-demand 비율 (0이면 전부 spot)
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.prefix}-asg-instance"
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