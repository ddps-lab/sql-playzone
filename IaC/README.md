# SQL Playground Infrastructure as Code

이 프로젝트는 SQL Playground CTFd 플랫폼을 위한 AWS 인프라를 Terraform으로 관리합니다.

## 원격 state

운영 state는 다음 S3 backend를 정본으로 사용합니다.

| 항목 | 값 |
|---|---|
| CloudFormation stack | `sql-playzone-terraform-state-backend` |
| bucket | `hyu-ddps-sql-playzone-tfstate-786382940258-ap-northeast-2` |
| region | `ap-northeast-2` |
| state key | `sql-playzone/prod/terraform.tfstate` |
| lock | Terraform native S3 lockfile (`use_lockfile = true`) |

bucket은 state bootstrap 순환을 피하기 위해 [`bootstrap/state-backend.yaml`](bootstrap/state-backend.yaml) CloudFormation stack으로 관리합니다. Versioning, SSE-S3, public access block, bucket-owner enforcement, TLS-only policy를 적용하고 stack 삭제 시에도 bucket과 policy를 retain합니다. 과거 version은 자동 만료하지 않습니다.

검증 기준 버전(2026-08-31):

| 구성요소 | 안정 버전 | 코드 constraint |
|---|---:|---:|
| Terraform CLI | `1.16.0` | `~> 1.16.0` |
| hashicorp/aws | `6.62.0` | `~> 6.62.0` |
| hashicorp/archive | `2.8.0` | `~> 2.8.0` |
| hashicorp/null | `3.3.1` | `~> 3.3.1` |
| hashicorp/time | `0.14.1` | `~> 0.14.1` |

`.terraform.lock.hcl`을 commit하며, provider를 갱신할 때는 공식 안정 release를 확인한 뒤 `terraform init -upgrade`와 plan을 별도 검토합니다. prerelease는 운영에 사용하지 않습니다.
현재 lock file은 `linux_amd64`와 `darwin_arm64` package checksum을 포함합니다.

bootstrap 또는 복구:

```bash
aws cloudformation deploy \
  --stack-name sql-playzone-terraform-state-backend \
  --template-file bootstrap/state-backend.yaml \
  --parameter-overrides StateBucketName=hyu-ddps-sql-playzone-tfstate-786382940258-ap-northeast-2 \
  --profile hyu-ddps \
  --region ap-northeast-2

aws cloudformation update-termination-protection \
  --enable-termination-protection \
  --stack-name sql-playzone-terraform-state-backend \
  --profile hyu-ddps \
  --region ap-northeast-2
```

로컬 초기화:

```bash
terraform init -reconfigure -backend-config="profile=hyu-ddps"
```

새 backend는 빈 state로 시작합니다. 2025년 환경의 잔존 VPC와 Aurora는 이 state가 관리하지 않습니다. 현재 기본 prefix `playzone`으로 apply하면 기존 자원 이름과 충돌할 수 있으므로, 신규 환경 prefix와 CIDR/log bucket을 먼저 확정하고 plan을 검토해야 합니다.

## 아키텍처

- **VPC**: Public/Private/Data 서브넷으로 구성
- **RDS**: MariaDB 데이터베이스 (프라이빗 서브넷)
- **EC2**: Auto Scaling Group with ALB
  - On-demand 인스턴스 1개 (기본)
  - Spot 인스턴스로 스케일 아웃
- **Route53**: 도메인 연결 (sql-playground.ddps.cloud)

## 사전 준비

1. AWS CLI 설정 및 프로필 구성
2. Terraform 설치
3. `private.auto.tfvars` 파일 생성:
```bash
cp private.auto.tfvars.example private.auto.tfvars
```

4. `private.auto.tfvars`의 placeholder를 실제 secret store와 AWS 설정에 맞게 교체합니다. 이 파일은 Git에서 ignore되며 commit하면 안 됩니다.

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
terraform init -reconfigure -backend-config="profile=hyu-ddps"
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
- 기본: 1개 On-demand 인스턴스
- 스케일 아웃: Spot 인스턴스 (최대 10개)
- 메트릭: ALB Request Count Per Target (300 requests)

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
2. **프로덕션**: On-demand 1개 + Spot으로 스케일링
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
