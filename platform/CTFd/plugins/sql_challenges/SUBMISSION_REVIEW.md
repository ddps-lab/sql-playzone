# 제출·성적 공정성 변경 검증

## 동작

SQL 전용 페이지와 제출 API는 같은 상태·선수 문제·팀 검사 함수를 사용합니다. 페이지에도 기존 CTFd의 공개 범위·시험 시간·이메일 검증 decorator를 적용합니다. 표준 challenge의 제출 로직은 유지하고 SQL의 접수·판정·저장을 `submissions.py`에서 처리합니다.

Go judge는 `error_kind`를 반환합니다. `student_query`만 학생 오답으로 해석하며 `problem`, `system`, 필드가 없는 구버전 응답과 알 수 없는 오류는 판정 불가입니다. 문구를 검색해 책임을 추측하지 않습니다. 정상 결과는 버전 1 공개 규약으로 비교합니다. 자세한 값·NULL·정렬·표시 규칙은 [AUTHORING.md](AUTHORING.md)에 있습니다.

Exam Mode는 매 요청에서 허용 학번을 검사하고 `Users.banned`를 쓰지 않습니다. 기존 ban을 자동 해제하지 않습니다. 성적 화면과 CSV는 모든 일반 사용자 계정을 포함하며 ban/hidden 상태를 표시합니다. CSV에는 `Banned`, `Hidden` 열이 추가됩니다. 수강생 범위는 학번으로 확인해야 하며 자동 cohort 선별 기능은 없습니다.

## 로컬 검증

CTFd 하네스 환경에서 다음을 실행합니다. DB는 테스트 전용 SQLite이고 학생·문제는 합성 데이터입니다. judge HTTP 응답만 mock하며 인증 훅·접근 검사·제출 저장·성적 CSV는 실제 경로를 사용합니다.

```sh
cd platform
TESTING_DATABASE_URL=sqlite:// python -m pytest -q -p no:randomly -p no:warnings \
  tests/users tests/oauth tests/plugins tests/test_views.py tests/test_themes.py \
  tests/api/v1/test_challenges.py tests/api/v1/challenges/requirements/test_requirements.py
```

저장소 루트에서:

```sh
npm --prefix platform/CTFd/themes/ddps run build:sql
node --test tests/js/*.test.cjs
python -m pytest -q tests/test_*.py
./scripts/test-sql-judge
```

테마 의존성은 `yarn install --frozen-lockfile`로 설치합니다. `build:sql`은 공유 import가 없는 SQL 화면·행동 tracker의 정적 번들과 manifest 항목만 재생성합니다. 기존 전체 테마 소스와 저장된 번들 사이의 무관한 차이는 함께 배포하지 않습니다. JS 검사는 실제 화면 함수와 최소 DOM/fetch stub을 사용합니다. Redis 잠금 검사는 `redis-server`가 설치되어 있으면 임시 Unix socket으로 별도 프로세스를 기동해 소유권·경쟁·만료 후 해제를 검사합니다. Go 통합 검사는 격리된 MySQL 8.4와 빌드한 judge 컨테이너를 사용하고 종료 시 컨테이너·볼륨을 정리합니다.

## DB 자격 증명과 행동 로그

`RDS_MASTER_SECRET_ARN`이 설정된 mysql+pymysql 연결은 새 연결 시 Secrets Manager의 `AWSCURRENT`를 사용합니다. 정상 조회는 60초 캐시하고, 접속 인증 오류 1045에만 강제 갱신 후 한 번 재연결합니다. 실행한 SQL이나 트랜잭션은 재시도하지 않습니다. Secrets Manager 일시 장애 시 기존 캐시로 연결을 시도하되, 인증 실패 뒤 갱신도 실패하면 명시적 연결 실패로 남깁니다. 시작 단계의 DB 확인·마이그레이션 엔진에도 같은 처리를 적용합니다.

EC2 컨테이너가 기존 instance role로 Secret을 읽을 수 있도록 IMDSv2를 필수로 하고 hop limit을 2로 설정합니다. 이 launch template 변경과 release를 함께 dev에 검증해야 합니다. IAM 권한 범위를 추가하지 않습니다. 기존 DB 비밀번호를 회전시키는 Terraform 변경은 아닙니다.

행동 로그는 허용 필드만 저장하고 문자열·메타데이터·본문 크기와 요청당 1,000개 이벤트 수를 제한합니다. 사용자·문제 식별자는 서버가 정하며 길이 값은 실제 텍스트에서 계산합니다. 클라이언트는 한 번에 최대 50개를 순서대로 전송하고, 일시 실패는 재시도하며, 영구적인 크기/형식 오류는 배치를 분리해 잘못된 이벤트가 후속 전송을 막지 않게 합니다. 학생 브라우저 로그는 조작 가능한 관측 자료이며 단독 부정행위 판정 근거가 아닙니다. 브라우저 종료·장기 오프라인에도 보존되는 영속 큐는 없습니다.

## dev 반영 후 확인

1. dev 병합 승인 후 CTFd와 judge를 같은 release로 빌드합니다. dev가 destroy된 상태이므로 plan 검토·apply 승인을 받은 뒤 기동합니다.
2. 합성 학생으로 공개·잠김·선수 문제·시작 전 접근을 페이지와 Test/Submit에서 확인합니다. 허용된 Test 실행의 서버 로그도 확인합니다.
3. 마감 직전 접수한 정답이 마감 후 완료돼도 제출 목록·점수·CSV에 같은 접수 시각으로 남는지 확인합니다.
4. judge 장애 응답 후 오답 횟수가 그대로인지, 정상 복구 후 마지막 남은 시도로 정답 제출이 되는지 확인합니다. 저장 실패 화면은 정답 완료로 표시하지 않아야 합니다.
5. 학생 기기 시계를 앞당기고 정상 문자열 `Sign In`을 반환하는 합성 문제로 제출합니다. 제출 제한은 세션 만료와 구분되어야 합니다.
6. Exam Mode 허용 학번을 바꾸면서 기존 로그인과 새 계정의 접근을 확인합니다. 기존 ban은 유지되고 성적 화면·CSV의 학생 행은 남아야 합니다. healthcheck와 관리자 접근도 확인합니다.
7. 기존 문제의 `grading_policy` 미확정 목록을 일괄 점검합니다. 지문에 맞춰 설정하고 학생 화면의 공개 기준과 관리자 Test를 확인합니다. 미확정 문제를 시험에 사용하지 않습니다.
8. 숫자 scale, 큰 정수, NULL/문자열 NULL, 중복 수, 순서 무관, 정렬 동률, 명시적 소수 표시를 합성 문제로 Test/Submit합니다.
9. dev의 앱 role로 현재 Secret을 읽고 새 DB 연결이 되는지 확인합니다. 실제 비밀번호 회전을 검증하려면 dev에 한정해 별도 승인받고, 연결 복구·캐시 갱신·기존 트랜잭션 보존을 확인합니다. 로컬 회전 테스트는 일회용 MySQL 계정으로 수행합니다.
10. 로그를 정상 입력·잘못된 추가 필드·긴 오프라인 backlog로 확인하고, CloudWatch 수집과 후속 이벤트 도착을 확인합니다.
11. 구버전 Exam Mode가 이미 변경한 ban의 원래 상태는 DB만으로 복원할 수 없습니다. 자동 일괄 해제하지 않고 관리자 기록과 대조합니다.

원본·지난 학기 데이터로 쓰기 테스트하지 않습니다. 로컬 검증과 PR 작성은 dev 병합·apply·main 병합 승인을 대신하지 않습니다.

## 2026-09-07 dev에서 확인한 배포 경로

새 MySQL 설치에서는 공통 Alembic migration 후 SQL 플러그인의 자체 migration이 테이블을 생성합니다. SQLite 하네스는 플러그인 migration 대신 `create_all()`을 사용하므로 이 순서 차이를 검증하지 못합니다. `add_grading_policy` 플러그인 revision이 마지막에 누락된 열을 추가하고, 공통 migration이 이미 만든 열은 보존합니다. `tests/test_sql_plugin_bootstrap.py`는 `SQL_MIGRATION_TEST_URL`로 지정한 **일회용 MySQL**에 별도 합성 DB를 만들어 실제 migration 순서를 검사하고 제거합니다. 운영 DB 주소를 넣지 않습니다.

Valkey Serverless는 서로 다른 hash slot의 키를 MGET으로 읽을 수 없습니다. 호환 backend는 기존 키·prefix·만료·직렬화·Redis 잠금을 유지하면서 `get_many`를 transaction 없는 GET pipeline으로 수행합니다. 기존 캐시나 로그인 세션을 일괄 삭제하거나 다른 namespace로 옮기지 않습니다.

시험 명단은 일반 설정의 자동 숫자 변환을 거치지 않고 저장된 문자열을 읽습니다. 학번 한 개만 등록하거나 앞자리에 0이 있어도 동일하게 접근을 검사해야 합니다. 새 dev release를 적용한 뒤 단일 학번의 허용·제외를 실제 학생 세션에서 재검증합니다.
