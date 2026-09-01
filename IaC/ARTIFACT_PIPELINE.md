# SQL Playzone 아티팩트 배포

이 문서는 `sql-2026-s2` 학기의 아티팩트 빌드와 dev 배포 절차를 설명합니다. 현재 검증 대상은 `dev` 브랜치와 `sql-dev.ddps.cloud` 환경입니다. main 반영과 운영 환경 배포는 운영자의 별도 승인을 받은 뒤에 진행합니다.

## 소유권

- Foundation Terraform은 학기 단위 ECR repository와 Packer builder IAM을 관리합니다.
- `build-release`, `set-channel-release`, `prune-artifacts`, `retire-channel` 명령은 SSM release parameter와 channel pointer를 관리합니다.
- Runtime Terraform은 SSM parameter를 읽고 manifest에 지정된 AMI와 ECR digest를 배포합니다.
- Application과 RDS 자격 증명은 EC2가 부팅할 때 Secrets Manager에서 읽습니다.

Foundation, dev runtime, production runtime은 서로 다른 Terraform state와 `TF_DATA_DIR`를 사용합니다. backend 설정 파일과 state 위치는 저장소에 커밋하지 않습니다.

## 필요한 도구

- Terraform `~> 1.16.0`
- Packer `~> 1.16.0`
- Packer Amazon plugin `1.8.2`
- AWS CLI와 `hyu-ddps` profile
- Python 3.12 이상

## Dev 검증 순서

1. Private backend 설정으로 `IaC/foundation`을 초기화하고 plan을 검토한 뒤 apply합니다.
2. Builder 도구나 Ubuntu base를 갱신할 때에는 release 빌드에 앞서 builder base AMI를 다시 만듭니다. 일반적인 release 빌드마다 실행할 필요는 없습니다.

   ```bash
   ./scripts/build-builder-base
   ```

3. 기능 브랜치를 원격에 push하고 full commit SHA를 사용하여 dev release를 빌드합니다.

   ```bash
   ./scripts/build-release --channel dev --commit "$(git rev-parse HEAD)"
   ```

   CTFd와 SQL Judge는 병렬로 빌드되며, channel별 BuildKit cache를 ECR에서 재사용합니다. Builder는 빌드 cache를 제거하고 실행에 필요한 image만 적재한 뒤 AMI를 생성합니다.

4. 운영 application secret의 OAuth 값과 새 CTFd key로 임시 dev secret을 만듭니다.

   ```bash
   ./scripts/prepare-dev-secret
   ```

5. Dev 전용 backend와 변수 파일로 runtime을 초기화하고 plan을 검토한 뒤 apply합니다.

   ```bash
   terraform -chdir=IaC plan -var-file=environments/dev.tfvars
   terraform -chdir=IaC apply -var-file=environments/dev.tfvars
   ```

6. HTTPS, ALB target health, CTFd 초기 설정, SQL Judge, Aurora, Valkey를 검증합니다.
7. 검증이 끝나면 dev runtime을 destroy하고 dev secret을 삭제합니다.

   ```bash
   terraform -chdir=IaC destroy -var-file=environments/dev.tfvars
   ./scripts/delete-dev-secret
   ```

8. `Deployment=sql-2026-s2-dev`에 해당하는 비용성 runtime 자원이 남아 있지 않은지 확인합니다.

## Release와 rollback

Runtime은 기본적으로 `/sql-playzone/sql-2026-s2/channels/dev/current`가 가리키는 release를 사용합니다. 기존 release로 되돌릴 때에는 같은 channel의 release를 선택한 뒤 Terraform을 apply합니다.

```bash
./scripts/set-channel-release --channel dev --release-id RELEASE_ID
terraform -chdir=IaC apply -var-file=environments/dev.tfvars
```

`prune-artifacts`는 기본적으로 삭제 예정 항목만 출력합니다. 실제 삭제에는 `--apply`가 필요합니다. current, previous, 활성 ASG·launch template·EC2가 참조하는 아티팩트는 보존됩니다.

```bash
./scripts/prune-artifacts
```

학기 종료 시에는 runtime을 먼저 제거하고 channel을 retire한 뒤 아티팩트를 정리합니다. Foundation은 ECR이 비워진 다음에 정리합니다.
