# 학생 실행·제출·성적 점검 가이드

문제를 게시하거나 서비스를 업데이트한 뒤, 학생이 정상적으로 풀고 제출할 수 있는지 확인하는 절차입니다. SQL을 알고 관리자 화면을 사용할 수 있으면 따라갈 수 있습니다. 개발 담당자용 자동 검증 참고는 문서 끝에 접어 두었습니다.

## 1. 점검 환경과 계정 준비

운영 담당자에게 다음을 확인해 주세요.

- **개발 환경(dev) 주소와 점검할 배포 버전**: dev는 시험 운영을 연습하는 서비스입니다. 켜져 있지 않다면 담당자에게 기동을 요청해야 합니다.
- **관리자 계정과 테스트용 학생 계정 A·B**: 관리자 계정은 접근 제한의 예외이므로 학생 동작은 학생 계정으로 확인해야 합니다. 관리자 **Users**에서 계정을 만들고 학번을 입력할 수 있습니다. 테스트 학생은 첫 로그인 때 필요한 ID·비밀번호·학번·약관 동의를 마쳐야 합니다.
- **설정을 바꿔도 되는 점검 시간**: 시험 시간·명단·브라우저 제한은 서비스 전체에 영향을 줍니다. 점검 전에 원래 설정을 기록해 주세요.

관리자와 학생은 서로 다른 브라우저 프로필로 로그인하는 것이 좋습니다. 같은 브라우저 창끼리는 로그인 상태를 공유할 수 있습니다. 테스트 계정에는 실제 학생과 겹치지 않는 학번을 사용해야 합니다.

## 2. 점검용 문제 준비

[출제 가이드](AUTHORING.md)의 **점검용 상품 조회** 예제를 dev에 만들어 주세요. 다음 설정을 확인합니다.

| 항목 | 점검 설정 |
|---|---|
| Points | 10 |
| 정렬 기준 | `2 desc, 1 asc` |
| 표시 형식까지 평가하는 열 번호 | 비워 둠 |
| Deadline (KST) | 처음에는 비워 둠 |
| State | Visible — 학생 계정이 열 수 있어야 합니다. |
| Max Attempts | 2 |

전체 시험 시간이 현재 접속을 허용하는지, 일시 중지와 시험 명단·브라우저·단일 세션 제한이 꺼져 있는지 확인해 주세요. 다른 조교가 점검 중이면 설정을 바꾸기 전에 조율해야 합니다.

## 3. Test와 Submit 확인

학생 A로 문제를 열고 아래 SQL을 차례로 실행해 주세요. 각 단계 뒤에 화면을 새로 고쳐 기록이 유지되는지 확인하는 것이 좋습니다.

### 먼저 Test로 실행 결과 확인

```sql
SELECT id, price
FROM products
WHERE price >= 2.50
ORDER BY price DESC, id ASC;
```

**Test**를 누르면 정답 안내와 상품 2·3의 결과가 보여야 합니다. Test는 실행 확인용이므로 이 단계에서는 성적에 10점이 추가되지 않아야 합니다.

### 오답을 Submit으로 제출

```sql
SELECT id, price FROM products WHERE id = 1;
```

**Submit**을 누르면 오답으로 기록되고 허용 횟수가 한 번 줄어야 합니다. 이 예제에서는 정답인 상품 2·3을 반환하지 않았으므로 오답이 맞습니다.

### 정답을 Submit으로 제출

처음의 정답 SQL로 바꿔 **Submit**을 눌러 주세요. 정답 기록과 10점이 반영돼야 합니다. 관리자 **Plugins → Submission Export**에서 학생 A의 문제 점수와 총점도 확인해 주세요. CSV 확인 방법은 [성적 내보내기 가이드](../submission_export/README.md)에 있습니다.

학생 B로 오답을 두 번 제출하면 이후 Submit이 횟수 제한으로 거부되는지도 확인할 수 있습니다. 다시 점검하려면 새 테스트 계정이나 새 점검용 문제를 사용하는 것이 좋습니다.

## 4. 공개 채점 기준 확인

학생 화면에 표시된 정렬·표시 형식 기준을 관리자 설정과 대조해 주세요. 아래는 같은 `products` 초기화 데이터를 사용해 **별도 점검용 문제**로 확인할 수 있는 예입니다. 표의 “정답 SQL”을 관리자 설정에 저장한 뒤 학생 화면에서 “학생 Test”를 실행하면 됩니다.

| 확인할 것 | 정답 SQL·설정 | 학생 Test | 예상 결과 |
|---|---|---|---|
| 숫자 표현 | `SELECT price FROM products;`, 정렬·표시 형식 빈 값 | `SELECT price + 0.000 FROM products;` | 정답. 숫자 값이 같음 |
| 실제 값 차이 | 위와 같음 | `SELECT price + 1 FROM products;` | 오답 |
| 중복 개수 | 위와 같음 | `SELECT DISTINCT price FROM products;` | 오답. 2.50의 개수가 줄어듦 |
| SQL NULL | `SELECT NULL AS result;`, 두 설정 빈 값 | `SELECT 'NULL' AS result;` | 오답. NULL과 문자열 구별 |
| 정렬 동률 | `SELECT id, price FROM products ORDER BY price DESC, id ASC;`, 정렬 `2 desc` | `SELECT id, price FROM products ORDER BY price DESC, id DESC;` | 정답. 같은 가격끼리의 순서는 자유로움 |
| 표시 형식 | `SELECT CAST(1 AS DECIMAL(10,2)) AS result;`, 표시 형식 열 `1` | `SELECT CAST(1 AS DECIMAL(10,1)) AS result;` | 오답. 1.00과 1.0의 표시 차이 |

실제 출제 문제의 지문도 해당 설정과 일치해야 합니다. 기존 문제에서 “채점 기준 확인 중” 안내가 나오면 관리자 화면에서 기준을 검토·저장해야 합니다.

## 5. 접근 제한·마감 확인

시험 시간은 서비스 전체에 적용되므로 dev에서 한 항목씩 바꾸고 원래 값으로 복원해 주세요.

| 점검 방법 | 예상 결과 |
|---|---|
| 점검용 문제를 Hidden으로 바꾸고 학생 계정으로 새로 열기 | 문제 접근이 제한됨 |
| 선수 문제를 지정하고, 그 문제를 풀기 전·후로 접근하기 | 선수 문제를 푼 뒤 접근 가능 |
| 전체 시작 시각을 미래로 설정하고 학생 화면·Test·Submit 확인 | 시작 전에 실행·제출이 제한됨 |
| 일시 중지 상태에서 Test·Submit 확인 | 두 동작 모두 제한됨 |
| 새 점검용 문제의 Deadline을 몇 분 뒤로 설정하고 마감 전·후 Submit | 마감 전 접수는 허용, 마감 후 새 제출은 거부됨 |

마감은 **서버가 접수한 시각**으로 판단합니다. 마감 전 접수한 답의 채점이 나중에 끝나도 접수 시각으로 기록돼야 합니다. 초 단위 경계나 채점 지연 상황은 개발 담당자가 자동 테스트로 확인하도록 요청하는 것이 좋습니다. 학생 기기의 시계는 화면 안내에 사용됩니다.

## 6. 시험 명단과 성적 확인

관리자 **Plugins → Exam Mode**에서 테스트 학생 A의 학번만 한 줄 입력하고 **Enable Exam Mode → Save & Apply**를 적용해 주세요.

1. 학생 A는 접근할 수 있고 B는 제한되는지 확인합니다. 이미 로그인한 학생도 새로고침 후 규칙이 적용돼야 합니다.
2. 명단을 B의 학번으로 바꿔 같은 방법으로 확인합니다.
3. 앞자리 0이 있는 테스트 학번을 한 개만 등록해 허용·제외를 확인하는 것이 좋습니다.
4. 관리자가 계속 접근할 수 있는지 확인한 뒤 명단 설정을 원래대로 복원해 주세요.
5. Submission Export 화면과 CSV에 학생 A·B의 행과 점수가 남아 있는지 확인합니다. 최종 성적 처리 때는 수강생 명단과 학번으로 대조해야 합니다.

같은 Exam Mode 화면에서 **Allow the exam browser only**를 켜면 지정 브라우저로만 학생이 접속할 수 있습니다. **Allow only one session per student**를 켜면 새 로그인이 이전 세션을 종료합니다. 이 두 설정은 아래쪽 **Save**로 저장해야 합니다. 학생의 첫 계정 설정을 마친 뒤 점검하고, 끝나면 각 스위치를 원래대로 복원해 주세요.

## 7. 오류가 보일 때의 조치

| 화면·증상 | 뜻 | 조교가 할 일 |
|---|---|---|
| 오답 | 학생 SQL 오류·실행 한도 위반·결과 불일치 | 지문·공개 기준·학생 결과를 대조해야 합니다. |
| 판정 불가 | 문제 설정·정답 오류 또는 채점 서버·통신 문제 | 관리자 Test로 문제를 확인하고, 여러 문제에서 반복되면 개발 담당자에게 로그 점검을 요청해야 합니다. 오답 횟수는 보존돼야 합니다. |
| 다른 쿼리 처리 중·요청이 너무 많음 | 계정의 동시 실행·분당 요청 한도 | 잠시 기다린 뒤 다시 실행하도록 안내할 수 있습니다. |
| 로그인 화면으로 이동 | 세션 만료 또는 다른 로그인에 의한 세션 종료 가능 | 다시 로그인하고 시험의 단일 세션 설정을 확인해 주세요. |
| 제출 저장 실패 | 기록 저장 중 문제 발생 | 학생의 제출 시각·문제·화면 메시지를 기록하고 담당자에게 확인을 요청해야 합니다. |

채점 장애가 해결되면 학생은 다시 제출할 수 있습니다. 새 제출은 새 접수 시각으로 마감을 판단하므로 마감이 지난 학생의 처리는 제출·장애 기록을 확인해 결정해야 합니다.

장애를 의도적으로 만드는 검사, DB 비밀번호 변경, 새 설치의 DB 구조 확인은 개발·배포 담당자에게 문서 끝의 기술 검증 항목을 요청하면 됩니다.

## 8. 점검 마무리와 인계

시험 시간·일시 중지·명단·브라우저·단일 세션 설정을 원래대로 복원하고 점검용 문제는 Hidden으로 바꿔 주세요. 다음 조교에게는 아래 형식으로 결과를 남기는 것이 좋습니다.

```text
점검 일시 / 서비스 주소 / 배포 버전:
점검한 문제와 테스트 계정(내부 식별자):
Test → 오답 Submit → 정답 Submit → CSV 확인 결과:
공개 기준 / 마감 / 명단 점검 결과:
실패 항목과 화면 메시지:
복원한 설정 / 추가 확인 담당자:
```

비밀번호·토큰과 학생의 실제 개인정보는 결과 문서에 넣지 말아 주세요.

## 개발 담당자용 검증 참고

<details>
<summary>자동 테스트 실행과 배포 후 기술 점검</summary>

### 자동 테스트 준비

Python 테스트는 `platform/development.txt`와 각 플러그인의 `requirements.txt`를 설치한 개발용 가상 환경에서 실행해야 합니다. `platform/CTFd/config.ini`가 없으면 `config.example.ini`를 복사해 준비해 주세요. 별도 checkout이나 worktree에도 이 설정 파일이 필요합니다.

**platform 디렉터리**에서 웹 요청·권한·접수·저장을 검사할 수 있습니다. 테스트용 SQLite와 가상 학생·문제를 사용하며 일부 judge 응답은 테스트에서 대체합니다.

```bash
TESTING_DATABASE_URL=sqlite:// \
SQL_JUDGE_SERVER_URL=http://127.0.0.1:18080 \
python -m pytest -q -p no:randomly -p no:warnings \
  tests/users tests/oauth tests/plugins tests/test_views.py tests/test_themes.py \
  tests/api/v1/test_challenges.py tests/api/v1/challenges/requirements/test_requirements.py
```

위 judge 주소는 테스트 중 자동 서버 빌드를 피하기 위한 설정입니다. 실제 MySQL 실행은 아래 `test-sql-judge`로 확인해야 합니다. **저장소 루트**에서는 다음 검사를 실행할 수 있습니다.

```bash
node --test tests/js/*.test.cjs
python -m pytest -q tests/test_*.py
./scripts/test-sql-judge
```

JavaScript 검사에는 Node.js, judge 검사에는 Docker·Compose v2·openssl이 필요합니다. judge 스크립트는 일회용 MySQL과 테스트 컨테이너를 만들고 종료 시 자기 자원을 정리합니다. Redis 잠금 테스트는 로컬 `redis-server`가 필요하며, 없으면 일부 검사가 skip됩니다. 실행 결과에 실패·skip 사유를 함께 기록해야 합니다.

SQL 화면을 수정했다면 Yarn Classic으로 의존성을 준비하고 정적 파일도 빌드해야 합니다.

```bash
yarn --cwd platform/CTFd/themes/ddps install --frozen-lockfile
npm --prefix platform/CTFd/themes/ddps run build:sql
```

`build:sql`은 SQL 화면·행동 tracker의 정적 파일과 manifest를 갱신합니다. 소스와 빌드 결과를 함께 검토해 주세요.

### 개발·배포 검증 항목

| 항목 | 확인 방법과 기대 동작 |
|---|---|
| 접수·장애 처리 | `platform/tests/plugins/test_sql_submission_lifecycle.py`로 마감 전 접수 후 지연 완료, 판정 불가 후 횟수 보존, 저장 실패, 학생 시계 차이와 세션 오류 구분을 확인해야 합니다. judge의 `error_kind=student_query`는 오답, `problem`·`system`과 알 수 없는 응답은 판정 불가로 처리됩니다. |
| 새 MySQL 설치 | `platform/tests/test_sql_plugin_bootstrap.py`에 일회용 MySQL 주소를 `SQL_MIGRATION_TEST_URL`로 전달합니다. 임시 DB를 생성·삭제하므로 개발 전용 계정이 필요합니다. 공통 migration 다음 플러그인 migration이 실행돼 `grading_policy` 열을 준비하고 기존 열의 값을 보존해야 합니다. dev 새 설치에서도 문제 생성·조회를 확인해야 합니다. |
| DB 비밀번호 | `RDS_MASTER_SECRET_ARN` 연결은 현재 Secret을 60초 캐시하고 새 연결의 인증 오류 1045에 한 번 갱신·재연결합니다. `platform/tests/test_database_secret.py`로 검사할 수 있습니다. 실제 AWS 회전 검사는 dev 대상과 복구 절차를 승인받은 뒤 수행해야 합니다. 컨테이너의 Secret 조회에는 인스턴스 역할·IMDSv2·hop limit 2 설정을 확인해 주세요. |
| 캐시·세션 | Valkey의 여러 키 조회는 GET pipeline을 사용합니다. 배포 뒤 기존 세션이 유지되고 CTFd 로그에 `CROSSSLOT` 오류가 없는지 확인해야 합니다. |
| 행동 로그 | 요청당 최대 1,000개, 클라이언트 배치당 최대 50개 이벤트의 필드·크기 제한과 재시도를 확인합니다. `platform/tests/plugins/test_behavior_events.py`와 JS 검사를 사용하고, dev에서 CloudWatch 도착도 확인해야 합니다. 브라우저 종료·장기 오프라인의 유실 가능성은 서버 기록과 함께 검토해야 합니다. |

dev 배포는 CTFd·judge를 같은 release로 준비하고 [배포 절차](../../../../IaC/ARTIFACT_PIPELINE.md)에 따라 plan 검토·승인·apply 후 진행해야 합니다. 현재 dev 기동 상태는 배포 담당자에게 확인해 주세요. 기술 검증 결과와 위 조교 점검 결과를 함께 기록하면 됩니다.

</details>
