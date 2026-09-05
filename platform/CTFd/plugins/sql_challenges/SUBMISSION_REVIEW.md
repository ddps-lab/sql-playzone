# 제출·성적 공정성 변경 검증

## 동작

SQL 전용 페이지와 제출 API는 같은 상태·선수 문제·팀 검사 함수를 사용합니다. 페이지에도 기존 CTFd의 공개 범위·시험 시간·이메일 검증 decorator를 적용합니다. 표준 challenge의 제출 로직은 유지하고 SQL의 접수·판정·저장을 `submissions.py`에서 처리합니다.

Go judge는 `error_kind`를 반환합니다. `student_query`만 학생 오답으로 해석하며 `problem`, `system`, 필드가 없는 구버전 응답과 알 수 없는 오류는 판정 불가입니다. 문구를 검색해 책임을 추측하지 않습니다. 정상 결과의 숫자·NULL·행 비교 방식은 이 변경에 포함하지 않습니다.

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
node --test tests/js/sql_submission.test.cjs
python -m pytest -q tests/test_*.py
./scripts/test-sql-judge
```

테마 의존성은 `yarn install --frozen-lockfile`로 설치합니다. `build:sql`은 공유 import가 없는 SQL 화면의 정적 번들과 manifest 항목만 재생성합니다. 기존 전체 테마 소스와 저장된 번들 사이의 무관한 차이는 함께 배포하지 않습니다. JS 검사는 실제 화면 함수와 최소 DOM/fetch stub을 사용합니다. Redis 잠금 검사는 `redis-server`가 설치되어 있으면 임시 Unix socket으로 별도 프로세스를 기동해 소유권·경쟁·만료 후 해제를 검사합니다. Go 통합 검사는 격리된 MySQL 8.4와 빌드한 judge 컨테이너를 사용하고 종료 시 컨테이너·볼륨을 정리합니다.

## dev 반영 후 확인

1. dev 병합 승인 후 CTFd와 judge를 같은 release로 빌드합니다. dev가 destroy된 상태이므로 plan 검토·apply 승인을 받은 뒤 기동합니다.
2. 합성 학생으로 공개·잠김·선수 문제·시작 전 접근을 페이지와 Test/Submit에서 확인합니다. 허용된 Test 실행의 서버 로그도 확인합니다.
3. 마감 직전 접수한 정답이 마감 후 완료돼도 제출 목록·점수·CSV에 같은 접수 시각으로 남는지 확인합니다.
4. judge 장애 응답 후 오답 횟수가 그대로인지, 정상 복구 후 마지막 남은 시도로 정답 제출이 되는지 확인합니다. 저장 실패 화면은 정답 완료로 표시하지 않아야 합니다.
5. 학생 기기 시계를 앞당기고 정상 문자열 `Sign In`을 반환하는 합성 문제로 제출합니다. 제출 제한은 세션 만료와 구분되어야 합니다.
6. Exam Mode 허용 학번을 바꾸면서 기존 로그인과 새 계정의 접근을 확인합니다. 기존 ban은 유지되고 성적 화면·CSV의 학생 행은 남아야 합니다. healthcheck와 관리자 접근도 확인합니다.
7. 구버전 Exam Mode가 이미 변경한 ban의 원래 상태는 DB만으로 복원할 수 없습니다. 자동 일괄 해제하지 않고 관리자 기록과 대조합니다.

원본·지난 학기 데이터로 쓰기 테스트하지 않습니다. 로컬 검증과 PR 작성은 dev 병합·apply·main 병합 승인을 대신하지 않습니다.
