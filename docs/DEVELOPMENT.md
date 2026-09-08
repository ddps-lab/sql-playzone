# 개발·자동 검증 가이드

코드를 수정하거나 배포 전 기술 검증을 맡은 사람을 위한 문서입니다. 조교의 브라우저 점검은 [제출 점검 가이드](../platform/CTFd/plugins/sql_challenges/SUBMISSION_REVIEW.md)에서 시작할 수 있습니다.

## 1. 소스와 도구 준비

[저장소 루트](../README.md)에서 시작합니다. 아래 명령은 Linux·WSL의 Bash를 기준으로 합니다. Python 테스트에는 Python 3.11과 빌드 도구가 필요하며, judge 통합 검사는 Docker·Compose v2·openssl을 사용합니다. 브라우저 코드 검사는 Node.js, 테마 빌드는 Yarn Classic을 사용합니다.

Python 테스트 환경은 다음처럼 준비할 수 있습니다.

```bash
cd platform
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r development.txt
for sql_plugin_requirements in CTFd/plugins/*/requirements.txt; do
  [ -f "$sql_plugin_requirements" ] && python -m pip install -r "$sql_plugin_requirements"
done
test -f CTFd/config.ini || cp CTFd/config.example.ini CTFd/config.ini
```

`config.ini`는 Git에서 제외된 설정 파일입니다. 별도 checkout이나 worktree에도 준비해야 합니다. Python 패키지 빌드에 실패하면 [platform/Dockerfile](../platform/Dockerfile)의 시스템 의존성을 확인해 주세요.

## 2. 웹 애플리케이션 자동 검사

다음은 **platform 디렉터리**에서 실행하는 예입니다. SQLite 임시 테스트 DB와 가상 학생·문제를 만들고 웹 요청·권한·저장을 검사합니다. SQL 서버 응답을 대체하는 테스트도 포함하므로 실제 MySQL 검사는 3단계에서 따로 실행해야 합니다.

```bash
TESTING_DATABASE_URL=sqlite:// \
SQL_JUDGE_SERVER_URL=http://127.0.0.1:18080 \
python -m pytest -q -p no:randomly -p no:warnings \
  tests/users tests/oauth tests/plugins tests/test_views.py tests/test_themes.py \
  tests/api/v1/test_challenges.py tests/api/v1/challenges/requirements/test_requirements.py
```

위 주소는 테스트에서 자동으로 별도 judge를 빌드·기동하지 않도록 지정한 값입니다. 실제 judge에 연결하는 기능 검사는 3단계 또는 dev에서 진행해야 합니다.

| 변경 영역 | 집중해서 볼 테스트 |
|---|---|
| 접수·마감·오답 횟수 | `platform/tests/plugins/test_sql_submission_lifecycle.py` |
| 동시 실행 잠금 | `platform/tests/plugins/test_sql_submission_redis.py` — 로컬 `redis-server`가 필요하며 없으면 일부 검사가 skip됩니다. |
| DB 비밀번호 갱신 | `platform/tests/test_database_secret.py` |
| 공개 채점 기준의 DB 저장 | `platform/tests/test_sql_policy_migration.py` |
| 새 MySQL 설치 | `platform/tests/test_sql_plugin_bootstrap.py` |
| 로그인 ID 이전 | `platform/tests/test_login_id_migration.py` |
| 행동 로그·시험 규칙 | `platform/tests/plugins/test_behavior_events.py`, `test_exam_mode.py`, `test_single_session.py` |

`passed`는 통과, `failed`는 실패, `skipped`는 해당 조건에서 실행하지 않은 검사입니다. 실패·skip 사유와 검사한 commit을 결과에 남겨야 합니다.

## 3. 실제 MySQL judge 검사

**저장소 루트**에서 실행해 주세요. 스크립트가 일회용 MySQL과 judge를 만들고 테스트 종료 시 자기 컨테이너·볼륨을 정리합니다. 호스트에 Go를 설치하지 않아도 Docker 안에서 검사할 수 있습니다.

```bash
./scripts/test-sql-judge
```

검사 범위는 쿼리 격리·권한·시간 제한·정리, MySQL 초기화 스크립트 호환, 숫자·NULL·정렬 비교와 HTTP 요청입니다. 명령 종료 코드와 테스트 출력을 확인해야 합니다.

문제 세트의 실제 SQL만 검사하려면 [문제 검토 가이드](../platform/CTFd/plugins/sql_challenges/REVIEW.md)를 따라 주세요. 다른 judge와 비교할 때는 `scripts/regrade-challenges --help`의 `--baseline-url`을 사용할 수 있습니다. 기본 검사와 다른 엔진 비교는 같은 입력·버전을 기록해야 결과를 해석할 수 있습니다.

Go를 직접 빌드할 경우 `platform/CTFd/plugins/sql_challenges`에서 `go build -o /tmp/sql-playzone-judge .`를 사용할 수 있습니다. 현재 구현은 여러 Go 소스 파일로 나뉘므로 패키지 전체를 빌드해야 합니다. 단독 실행에는 격리된 MySQL 8.4와 `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_ROOT_PASSWORD`가 필요합니다.

## 4. JavaScript·저장소 검사

Python 가상 환경을 활성화한 상태로 **저장소 루트**에서 실행해 주세요.

```bash
node --test tests/js/*.test.cjs
python -m pytest -q tests/test_*.py
```

SQL 화면 소스를 수정했다면 [학생 테마 안내](../platform/CTFd/themes/ddps/README.md)에 따라 정적 파일을 다시 빌드해야 합니다. 배포는 Git에 저장된 정적 파일을 사용하므로 소스와 빌드 결과를 함께 검토해야 합니다.

## 5. 로컬 웹 실행에 필요한 설정

`platform/docker-compose.yml`은 개발용 소스 mount를 사용하며 다음 파일·연결을 준비해야 합니다.

| 준비물 | 내용 |
|---|---|
| `platform/CTFd/config.ini` | 예제에서 복사한 CTFd 설정 |
| `platform/.env` | CTFd용 `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `SQL_JUDGE_SERVER_URL=http://sql-judge:8080` 등 |
| `platform/.env.judge` | `MYSQL_HOST=mysql-judge`, `MYSQL_PORT=3306`, 로컬 채점 DB 전용 `MYSQL_ROOT_PASSWORD` |
| 서비스 DB·Redis | CTFd 컨테이너가 접속할 수 있는 개발 전용 주소·계정. Compose 파일의 db·cache 서비스는 주석 상태이므로 직접 준비해야 합니다. |

DB·Redis 연결과 파일 권한을 준비한 뒤 **platform 디렉터리**에서 `docker compose up -d --build`로 시작할 수 있습니다. Nginx는 호스트 80, CTFd는 8000 포트를 사용합니다. `docker compose ps`와 `docker compose logs ctfd sql-judge mysql-judge`로 기동을 확인한 뒤 브라우저에서 초기 관리자 설정을 진행해 주세요.

공용 개발 서버에서는 로그·첨부 볼륨의 소유권과 서비스 포트 노출을 담당자와 확인해야 합니다. 채점 DB 비밀번호는 최초 MySQL 볼륨 생성 때 적용되므로 기존 볼륨이 있다면 그 자격 증명을 사용해야 합니다.

## 6. 배포 담당자와 확인할 기술 항목

### 새 설치와 DB 구조 변경

DB 구조의 버전을 바꾸는 작업을 migration이라고 부릅니다. CTFd 공통 migration이 먼저 실행되고 SQL 플러그인의 migration이 테이블을 준비합니다. `add_grading_policy`는 채점 기준 열이 없으면 추가하고 이미 있으면 보존합니다.

`platform/tests/test_sql_plugin_bootstrap.py`는 `SQL_MIGRATION_TEST_URL`에 지정한 **개발 전용 일회용 MySQL** 안에 임시 DB를 만들고 제거합니다. 이 주소는 해당 서버에서 DB 생성·삭제가 가능한 테스트 계정이어야 합니다. 준비한 담당자가 다음처럼 실행할 수 있습니다.

```bash
# platform 디렉터리, SQL_MIGRATION_TEST_URL은 비공개 환경변수로 준비
TESTING_DATABASE_URL=sqlite:// python -m pytest -q tests/test_sql_plugin_bootstrap.py
```

SQLite 테스트는 자체 테이블 생성 경로를 사용하므로, 새 dev 설치에서도 migration 완료와 SQL 문제 생성·조회가 되는지 확인해야 합니다.

### DB 비밀번호 변경 대응

`RDS_MASTER_SECRET_ARN`을 사용하는 연결은 Secrets Manager의 현재 값(`AWSCURRENT`)을 조회하고 60초 캐시합니다. 새 연결에서 인증 오류 1045가 나면 한 번 강제 갱신·재연결합니다. 진행 중인 SQL·트랜잭션은 그 연결의 결과로 처리됩니다. Secret 조회 장애 시에는 보유한 캐시로 연결을 시도하며 갱신·인증에 실패하면 연결 실패로 기록합니다.

실제 AWS 비밀번호 회전 검사는 대상 dev와 복구 절차를 승인받은 뒤 진행해야 합니다. 새 연결 복구, Secret 조회 권한과 기존 트랜잭션 결과를 확인해 주세요. EC2의 IMDSv2·hop limit 2 설정은 컨테이너가 인스턴스 역할로 Secret을 읽는 데 사용됩니다.

### 캐시·로그·장애 응답

- Valkey Serverless의 `get_many`는 여러 GET을 묶어 전송하는 pipeline을 사용합니다. 기존 키·직렬화·세션을 유지하면서 여러 hash slot에 걸친 MGET 오류를 피합니다. 배포 후 세션 유지와 `CROSSSLOT` 로그를 확인해야 합니다.
- judge의 오류 분류 `student_query`는 학생 오답, `problem`·`system`과 알 수 없는 응답은 판정 불가로 처리합니다. 장애 응답 뒤 시도 횟수 보존·재제출을 자동 테스트로 확인해야 합니다.
- 행동 로그는 요청당 최대 1,000개 이벤트를 받고 허용 필드·크기를 검사합니다. 클라이언트는 최대 50개씩 전송하고 오류 배치를 분리·재시도합니다. 브라우저 종료·장기 오프라인 시 유실 가능성을 고려해 서버 기록과 함께 검토해야 합니다.
- 마감 직전 접수 후 지연 완료, 저장 실패, 학생 시계 차이, 일반 문자열 `Sign In` 응답, 긴 로그 대기열은 자동 테스트에서 재현하는 것이 좋습니다. 조교에게는 [제출 점검 결과](../platform/CTFd/plugins/sql_challenges/SUBMISSION_REVIEW.md)와 함께 전달해 주세요.

## 7. 변경 제출

관련 변경과 검증 결과를 하나의 dev 대상 PR로 정리한 뒤 병합 승인을 받아야 합니다. 필요하면 병합 후 [배포 가이드](../IaC/ARTIFACT_PIPELINE.md)에 따라 dev에서 기능을 확인합니다. main 병합은 운영자의 명시적인 지시 후 진행해야 합니다.

commit·PR 본문에는 변경 내용과 검증을 적고 attribution·세션 metadata trailer는 붙이지 않습니다. 비공개 문제, 정답, 학생 정보와 Secret 값은 Git·PR에 넣지 않아야 합니다.
