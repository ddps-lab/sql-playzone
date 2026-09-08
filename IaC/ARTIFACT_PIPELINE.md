# 서비스 배포 가이드

개발 환경 기동, 새 버전 배포, 이전 버전 복원과 환경 종료를 안내합니다. AWS·Terraform 권한을 받은 배포 담당자가 진행해야 합니다. 새 조교는 [운영 가이드](../docs/TA_OPERATIONS.md)로 화면 작업을 익힌 뒤 필요한 배포를 담당자에게 요청할 수 있습니다.

## 1. 배포 단위 이해하기

| 용어 | 의미 |
|---|---|
| release | 특정 소스 commit에서 만든 CTFd·judge 이미지와 서버 이미지(AMI)를 묶은 배포 버전 |
| manifest | release의 소스 commit·AMI·이미지 식별값(digest)을 기록한 구성 목록 |
| channel | dev 또는 main의 현재 release를 선택하는 경로. AWS SSM Parameter Store에 저장합니다. |
| foundation | 이미지 저장소(ECR), 빌드 권한 등 학기 단위 기반 자원 |
| runtime | 실제 서비스를 실행하는 EC2·ALB·Aurora·Valkey·첨부 S3 등 환경별 자원 |
| plan / apply | Terraform 변경 예정 내역 확인 / 검토한 변경 적용 |

기본 `artifact_prefix`는 `sql-2026-s2`입니다. 새 학기는 이름·비밀 설정·백업 계획을 먼저 정해야 합니다. 인프라 구조와 시험 예약 확장은 [AWS 운영 가이드](README.md)를 참고해 주세요.

## 2. 권한·도구·환경 설정 인계

준비할 도구는 Git, Python 3.12 이상, AWS CLI, Terraform `~> 1.16.0`, Packer `~> 1.16.0`과 Amazon plugin `1.8.2`입니다. 버전 요구는 이 저장소의 빌드 설정을 기준으로 합니다.

다음 자료는 기존 배포 담당자에게 받아야 합니다.

- AWS profile과 접근 권한. 스크립트 기본 profile은 `hyu-ddps`, region은 `ap-northeast-2`입니다.
- foundation·dev·운영 각각의 **backend 설정 파일**, **TF_DATA_DIR**, **tfvars**.
- 로컬 `IaC/private_var.tf`의 AWS 계정·프로필·DB 사용자·Route 53·SSH key 이름 설정. 형식은 [private_var.tf.example](private_var.tf.example)을 참고할 수 있습니다.
- 애플리케이션 Secret의 이름·접근 방법과 현재 release, 복구용 백업 위치.

backend는 Terraform 상태의 저장 위치입니다. backend 파일에는 bucket·key·region 등 연결 설정이 들어갑니다. TF_DATA_DIR는 해당 연결 정보를 저장하는 로컬 디렉터리입니다. **foundation·dev·운영의 연결 자료는 각각 짝을 맞춰 사용해야 합니다.**

### dev 연결 예시

이하 명령은 Bash의 **저장소 루트**에서 실행합니다. `실제 ... 경로` 부분은 인계받은 절대 경로로 바꿔야 합니다. plan 파일은 이번 작업 전용 경로를 정해 주세요.

```bash
export AWS_PROFILE=hyu-ddps
export AWS_DEFAULT_REGION=ap-northeast-2
export TF_DATA_DIR='/실제/dev 전용 terraform 데이터 경로'
sql_backend='/실제/dev backend 설정 파일 경로'
sql_plan='/실제/비공개 작업 경로/dev.tfplan'
aws sts get-caller-identity --profile "$AWS_PROFILE" --region "$AWS_DEFAULT_REGION"
terraform -chdir=IaC init -reconfigure -backend-config="$sql_backend"
terraform -chdir=IaC workspace show
terraform -chdir=IaC state list
```

계정·backend key·기존 자원 이름이 dev 대상인지 확인해야 합니다. 새 환경이면 state가 비어 있을 수 있습니다. 운영은 운영 backend·TF_DATA_DIR·tfvars로 연결하고 `artifact_channel = "main"`, `deployment_mode = "persistent"`인지 확인해야 합니다.

## 3. 처음 준비하는 기반 자원

foundation이 이미 있으면 4단계로 진행할 수 있습니다. 처음 만드는 학기라면 foundation용 연결 자료로 `terraform -chdir=IaC/foundation init -reconfigure -backend-config=...`를 실행하고, 해당 학기의 `artifact_prefix`로 전체 plan을 검토·승인받아 apply해야 합니다.

이전 Terraform 구성에 같은 이름의 ECR 저장소가 있다면 기존 상태에서의 소유권을 옮기는 작업이 필요합니다. 담당자는 기존 이미지를 보존한 채 foundation에 import하고 이전 state의 참조를 정리한 뒤 다음 단계로 진행해야 합니다. `RepositoryAlreadyExists`가 나오면 자원 이름·소유 state부터 확인해 주세요.

빌드 도구를 담은 기반 AMI가 없거나 도구·OS를 갱신할 때는 다음 명령을 사용합니다. AWS 자원을 생성하므로 사전에 실행 범위를 승인받아야 합니다.

```bash
./scripts/build-builder-base
```

애플리케이션 Secret에는 CTFd key와 Google OAuth 설정이 필요합니다. RDS 비밀번호는 RDS 관리 Secret을 사용합니다. dev Secret이 없을 때는 승인 후 `./scripts/prepare-dev-secret`으로 생성할 수 있습니다. 이 명령은 운영 OAuth 설정을 읽고 새 dev key를 만들며, 이미 존재하는 Secret은 재사용해야 합니다.

## 4. 새 release 빌드

프로젝트 절차는 **기능 브랜치 검증 → dev 대상 PR → 병합 승인 → dev 병합 → 빌드·배포 확인**입니다. main 병합은 dev 확인 후 운영자의 명시적 지시에 따라 진행해야 합니다.

원격에 push된 대상 브랜치의 전체 commit SHA를 확인한 뒤 빌드해 주세요.

```bash
./scripts/build-release --channel dev --commit <전체-dev-병합-commit-SHA>
```

명령의 `<...>`는 실제 SHA로 바꿔야 합니다. main 배포는 승인된 main 병합 SHA와 `--channel main`을 사용합니다. 학기 이름·profile·region이 기본값과 다르면 각 스크립트의 `--help`를 확인해 동일한 값을 전달해야 합니다.

빌드는 CTFd·judge 이미지를 만들고 AMI·manifest를 저장한 뒤 channel의 현재 release를 갱신합니다. 완료 로그의 release ID를 기록해 주세요. 실행 중인 서버는 다음 apply 단계에서 새 버전으로 교체됩니다.

## 5. plan 검토·apply·기능 확인

2단계에서 연결한 dev 예시는 다음과 같습니다.

```bash
terraform -chdir=IaC plan -var-file=environments/dev.tfvars -out="$sql_plan"
terraform -chdir=IaC show -no-color "$sql_plan"
```

검토할 항목:

- 자원 이름·도메인·backend가 모두 의도한 환경인지
- 배포할 release·AMI가 이번 빌드와 일치하는지
- 생성·변경·삭제 범위가 작업 목적에 맞는지
- DB·첨부 보존과 시험 예약에 영향을 주는 변경이 있는지

승인받은 plan을 적용할 때는 다음을 실행하면 됩니다. plan에는 민감한 설정이 들어갈 수 있으므로 비공개 경로에 보관해야 합니다.

```bash
terraform -chdir=IaC apply "$sql_plan"
```

apply가 끝나면 ASG의 **Instance refresh**가 완료되고 모든 대상이 healthy인지 확인해야 합니다. 새 설치에는 관리자 초기 설정이 필요합니다. 기존 환경은 교체 전 로그인 세션이 유지되는지 확인하는 것이 좋습니다.

이어서 [제출 점검 가이드](../platform/CTFd/plugins/sql_challenges/SUBMISSION_REVIEW.md)의 Test·Submit·성적·명단 검사와 첨부 업로드·다운로드, CloudWatch 로그 수집을 확인해 주세요. CTFd·judge 이미지가 같은 manifest에 기록된 digest인지도 배포 담당자가 대조해야 합니다.

빌드·설정·인프라 상태가 바뀌었거나 이미 적용한 plan이면 새로 만들어 검토해야 합니다. 기동 상태·배포 버전·검증 결과·남은 항목은 날짜와 함께 배포 기록에 남겨 주세요.

## 6. 이전 release로 되돌리기

대상 tfvars의 `artifact_release_id = null`이면 channel의 현재 버전을 사용합니다. ID를 지정했다면 그 버전으로 고정되므로 되돌릴 때 이 설정도 함께 확인해야 합니다.

먼저 이전 앱과 현재 DB 구조의 호환성을 확인해야 합니다. 앱 버전을 되돌려도 DB 구조·데이터는 현재 상태를 유지합니다. DB 복구가 필요하면 백업과 별도 복구 절차를 준비해야 합니다.

```bash
./scripts/set-channel-release --channel dev --release-id <이전-release-ID>
```

버전 선택 후 5단계처럼 새 plan을 만들고 승인·apply·교체 완료·기능 확인을 진행해 주세요.

## 7. 환경 종료와 파일 정리

dev를 계속 사용할지 삭제할지는 운영자가 결정해야 합니다. 삭제 승인 전에는 필요한 DB·첨부 자료의 보관과 삭제 대상을 확인해 주세요. 현재 Aurora 설정은 삭제 시 최종 스냅샷을 생략합니다.

dev 연결 상태에서 검토용 삭제 plan을 만들 수 있습니다.

```bash
terraform -chdir=IaC plan -destroy -var-file=environments/dev.tfvars -out="$sql_plan"
terraform -chdir=IaC show -no-color "$sql_plan"
```

삭제 대상 전체를 승인받은 뒤 `terraform -chdir=IaC apply "$sql_plan"`을 실행해야 합니다. 삭제 후 EC2·Aurora·ALB·Valkey 등 비용이 발생하는 자원이 남았는지 확인해 주세요. 다음 기동 때 dev Secret을 재사용할지 폐기할지도 정해야 합니다. 폐기하기로 한 경우에는 `scripts/delete-dev-secret`의 대상을 확인해 사용할 수 있습니다.

학기 종료 시에는 runtime 종료 → `scripts/retire-channel`로 channel 사용 종료 → `scripts/prune-artifacts`로 배포 파일 정리 → 비워진 foundation 정리 순서로 진행합니다. 각 스크립트의 `--help`로 대상 인자를 확인해 주세요.

`scripts/prune-artifacts`는 기본적으로 삭제 예정만 보여 주며 실제 삭제는 `--apply`가 필요합니다. 현재·이전 release와 사용 중인 ASG·인스턴스가 참조하는 파일은 보호합니다. 운영 첨부 버킷을 비우거나 DB 삭제 보호를 해제하는 작업은 백업·보관 계획과 함께 따로 검토해야 합니다.
