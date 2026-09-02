# SQL Playground Infrastructure as Code

이 프로젝트는 SQL Playground CTFd 플랫폼을 위한 AWS 인프라를 Terraform으로 관리합니다.

## 아키텍처

- **VPC**: Public/Private/Data 서브넷으로 구성
- **RDS**: MariaDB 데이터베이스 (프라이빗 서브넷)
- **EC2**: Auto Scaling Group with ALB
  - On-demand 인스턴스 1개 (기본)
  - Auto Scaling으로 스케일 아웃 (기본 On-demand, 선택적으로 Spot)
- **Route53**: 도메인 연결 (sql-playground.ddps.cloud)

## 사전 준비

1. AWS CLI 설정 및 프로필 구성
2. Terraform 설치
3. `private_var.tf` 파일 생성:
```bash
cp private_var.tf.example private_var.tf
```

4. `private_var.tf`에 다음 값 설정:
```hcl
variable "db_username" {
    type        = string
    default     = "your_db_username"
    sensitive   = true
}

variable "db_password" {
    type        = string
    default     = "your_secure_password"
    sensitive   = true
}

variable "hosted_zone_id" {
    type        = string
    default     = "your_route53_hosted_zone_id"
}
```

## AWS 프로필 설정

특정 AWS 프로필을 사용하려면:
```bash
# var.tf에서 기본값 변경
variable "aws_profile" {
  default = "your-profile-name"
}

# 또는 terraform 실행 시 지정
terraform plan -var="aws_profile=your-profile-name"
terraform apply -var="aws_profile=your-profile-name"
```

## 모듈별 관리

### 전체 인프라 배포
```bash
terraform init
terraform plan
terraform apply
```

### VPC 모듈만 배포
```bash
terraform apply -target=module.vpc
```

### RDS 모듈만 배포 (VPC 필요)
```bash
terraform apply -target=module.vpc -target=module.rds
```

### EC2 모듈만 배포 (VPC, RDS 필요)
```bash
terraform apply -target=module.ec2
```

## 모듈별 삭제

### EC2만 삭제 (RDS 유지)
```bash
terraform destroy -target=module.ec2
```

### 전체 삭제 (RDS 보호 중)
RDS는 `deletion_protection = true`로 설정되어 있어 실수로 삭제되지 않습니다.
RDS를 삭제하려면:

1. `rds/rds.tf`에서 `deletion_protection = false`로 변경
2. `terraform apply -target=module.rds`로 설정 업데이트
3. `terraform destroy`로 전체 삭제

## 운영 관리

### Auto Scaling 설정
- 기본: On-demand 1개 (`asg_min_size`, `asg_desired_capacity`)
- 스케일 아웃: 최대 10개 (`asg_max_size`). `on_demand_percentage_above_base`가 100(기본)이면 추가 인스턴스도 On-demand이고, 0으로 두면 Spot으로 늘어납니다.
- 메트릭: ALB Request Count Per Target (분당 300 requests)
- `health_check_grace_period`와 instance refresh의 `instance_warmup`은 300초입니다. 첫 부팅이 MySQL 초기화와 judge healthcheck를 기다리므로, ALB healthy까지 3분 50초가 걸린 실측(2026-09-02, spot t4g.small)에 여유를 둔 값입니다.
- `desired_capacity`와 `min_size`는 생성 이후 Terraform이 되돌리지 않습니다(`ignore_changes`). 스케일링과 예약 작업이 바꾼 값을 시험 중 apply가 원래대로 줄이지 않게 하기 위한 것이며, 두 값을 바꾸려면 콘솔이나 CLI로 직접 조정합니다.

### 시험·퀴즈 사전 스케일
target tracking은 인스턴스를 추가하는 데 3~5분이 걸려 시험 시작 직후 burst를 따라가지 못합니다. `exam_windows`에 창을 선언하면 시작 시각에 최소·목표 용량을 `capacity`로 올리고, 종료 시각에 최소 용량만 되돌립니다. 이후 부하가 줄면 target tracking이 서서히 줄입니다.

```hcl
exam_windows = [
  { name = "midterm", start = "2026-10-20T08:30:00", end = "2026-10-20T11:30:00", capacity = 8 },
]
```

- 시각은 KST이며 시간대 접미사를 붙이지 않습니다. 시작은 시험 30분 전, 종료는 시험이 끝나고 30분 뒤로 잡습니다.
- 창을 추가하거나 고친 뒤 plan을 검토하고 apply해야 예약이 등록됩니다. 등록된 예약은 콘솔의 Auto Scaling group > Automatic scaling > Scheduled actions에서 확인합니다.
- 지난 창은 plan에서 자동으로 제외되므로 시험이 끝나면 항목을 지웁니다.
- 창끼리 겹치거나 맞닿으면 안 됩니다. 연달아 보는 시험은 한 창으로 합칩니다. `capacity`는 `asg_min_size` 이상 `asg_max_size`(기본 10) 이하여야 하며, 더 필요하면 `asg_max_size`를 먼저 올립니다.
- 인스턴스당 채점 상한은 초당 5~8건이며 지난 학기 시험은 8대로 운영했습니다.

### 인스턴스 타입 변경
`var.tf`에서 수정:
```hcl
variable "ondemand_server_instance_class" {
    default = "t3.small"  # On-demand 인스턴스 타입
}
```

### RDS 인스턴스 타입 변경
```hcl
variable "database_instance_class" {
    default = "db.t3.medium"  # RDS 인스턴스 타입
}
```

## 비용 최적화

1. **개발 환경**: EC2만 destroy하고 RDS는 유지
2. **프로덕션**: 평소 On-demand 1개. 스케일 아웃 인스턴스도 기본 On-demand이며(t4g.small 기준 시간당 약 $0.02), Spot으로 바꾸려면 `on_demand_percentage_above_base = 0`으로 둡니다.
3. **RDS 백업**: 7일 자동 백업 설정

## 보안 고려사항

- RDS는 프라이빗 서브넷에 위치
- EC2는 ALB를 통해서만 접근 가능
- SSH 접근 비활성화 (프로덕션)
- 모든 EBS 볼륨 암호화

## 문제 해결

### RDS 연결 실패
- Security Group 규칙 확인
- EC2 인스턴스의 Security Group이 RDS에 허용되어 있는지 확인

### 도메인 연결 실패
- Route53 Hosted Zone ID 확인
- ALB가 정상적으로 생성되었는지 확인
