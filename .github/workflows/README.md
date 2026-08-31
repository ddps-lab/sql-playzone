# GitHub Actions workflow 관리

## Upstream lint workflow

CTFd upstream의 `lint.yml`은 이 저장소에서 의도적으로 제거한 상태로 유지합니다.

과거에는 자동 실행을 막기 위해 `on` 항목만 주석 처리했지만, GitHub Actions가 이를 유효하지 않은 workflow로 판단하여 push마다 job과 log가 없는 실패 기록을 생성했습니다. 실행하지 않는 workflow는 `.github/workflows/`에 유효하지 않은 YAML 파일로 남겨 두지 않습니다.

또한 upstream workflow는 애플리케이션이 저장소 루트에 있고 기본 branch가 `master`라고 가정합니다. 이 저장소는 CTFd를 `platform/` 아래에서 관리하며 기본 branch로 `main`을 사용하므로, upstream workflow를 그대로 실행할 수 없습니다.

향후 upstream을 동기화할 때에는 `lint.yml`을 자동으로 복원하지 않습니다. CI가 필요하면 다음 사항을 반영한 DDPS 전용 workflow를 별도로 추가합니다.

- trigger와 branch 조건은 `main`을 기준으로 설정합니다.
- 명령과 파일 경로는 `platform/`을 기준으로 설정합니다.
- 현재 DDPS custom code의 lint 결과를 검토하고 통과 기준을 명시합니다.
- 실제로 통과하는 workflow를 확인한 뒤 required check 적용 여부를 결정합니다.

upstream에서 삭제된 `lint.yml`을 변경한 경우에는 이를 단순 반영하지 않고, 위 조건에 맞게 다시 도입할 필요가 있는지 검토합니다.
