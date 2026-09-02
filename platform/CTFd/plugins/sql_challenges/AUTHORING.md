# SQL 문제 출제 가이드

문제를 만들기 전에 한 번 읽어 주세요. 이 플랫폼은 여러분이 로컬 MySQL에서 쓰던 스크립트를 대부분 그대로 받지만, 채점기가 실행하는 방식이 로컬과 달라서 알아 두어야 할 점이 있습니다. 문제를 저장한 뒤에는 반드시 관리자 화면의 **Test**로 init과 정답을 한 번 실행해 보세요.

## 채점기가 실행하는 방식

| 항목 | 동작 |
|---|---|
| 실행 단위 | 제출마다 정답 쿼리와 학생 쿼리를 각각 **새 임시 데이터베이스**에서 실행하고 바로 삭제합니다. |
| init | 문제의 init SQL을 매번 처음부터 실행합니다. 이전 실행의 데이터는 남지 않습니다. |
| 계정 | init은 그 임시 DB에 모든 권한을 가진 계정으로, 정답·학생 쿼리는 **SELECT만** 가능한 계정으로 실행합니다. |
| 세션 | init과 채점 쿼리는 다른 연결이지만, init에서 `SET SQL_MODE=...`로 바꾼 값은 채점 쿼리에도 그대로 적용됩니다. 로컬에서 스크립트를 돌린 뒤 같은 창에서 쿼리하는 것과 같습니다. |
| 시간 | init + 쿼리 한 번에 2.5초, 요청 전체(정답 + 학생) 8초. 넘으면 오류로 채점됩니다. |
| 크기 | 요청 본문 1MiB, 결과 1,000행 또는 4MiB. |
| MySQL | 8.4, `utf8mb4_0900_ai_ci`(문자열 비교·정렬은 대소문자 구분 없음), 테이블명 대소문자 구분 없음(Windows·macOS 로컬과 동일). |

## init SQL

**그대로 붙여도 되는 것**

- MySQL Workbench나 mysqldump로 내보낸 스크립트. `DROP SCHEMA IF EXISTS kbo;`, `CREATE SCHEMA kbo;`, `USE kbo;`는 실행하지 않고 임시 DB로 매핑합니다. `kbo.PLAYER`처럼 스키마를 붙인 이름도 임시 DB로 바뀝니다.
- `SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL';` 같은 세션 설정, `/*!40101 SET ... */` 헤더, `LOCK TABLES`, `SET autocommit=0; ... COMMIT;`.
- 문장 앞의 `-- 주석`, `/* 주석 */`, `-----` 구분선.

**안 되는 것**

- 스키마 두 개 이상을 만들어 조인하는 스크립트. 모두 같은 임시 DB로 합쳐지므로 같은 이름의 테이블이 있으면 충돌합니다. 스키마는 하나만 쓰세요.
- `DELIMITER`, 프로시저·함수·트리거의 `BEGIN ... END` 본문, 문자열 값 안의 세미콜론. 문장은 단순히 `;`로 나뉩니다.
- 문장 **중간**에 끼어 있는 `-----` 줄. MySQL은 `--` 뒤에 공백이 없으면 주석으로 보지 않습니다.
- `FLUSH`, `SET GLOBAL`, 계정·권한 문장.
- `START TRANSACTION`을 열고 `COMMIT` 없이 끝나는 스크립트. init 연결이 닫히면서 롤백됩니다.

**권장**

- `CREATE SCHEMA`의 문자셋 옵션은 무시됩니다. 문자열 정렬이 중요하면 열에 `COLLATE`를 직접 지정하세요.
- `SET SQL_MODE`를 쓰면 그 모드가 학생 쿼리에도 적용됩니다. 예를 들어 `'TRADITIONAL'`은 `ONLY_FULL_GROUP_BY`를 끄므로 `GROUP BY`에 없는 열을 SELECT해도 통과합니다. SET이 없으면 MySQL 8 기본값(strict, `ONLY_FULL_GROUP_BY` 켜짐)입니다. 어느 쪽을 의도하는지 정하고 명시하세요.
- 데이터가 크면 Test에서 걸리는 시간을 확인하세요. 250KB(INSERT 수천 행) init이 운영 인스턴스에서 약 0.7초입니다.

## 정답 SQL

- **단일 SELECT 문**만 가능합니다. 여러 문장, DML, DDL, `USE`는 학생 쿼리와 마찬가지로 거부됩니다.
- 채점은 정답과 학생 쿼리의 **결과 행을 문자열로 순서대로 비교**합니다. 열 이름(별칭)은 비교하지 않고, 열 개수와 행 개수는 비교합니다. `NULL`은 `NULL`이라는 문자열로 표시됩니다.
- 따라서 **정렬 기준이 결과를 유일하게 결정해야 합니다.** `ORDER BY HEIGHT DESC`만 있으면 키가 같은 선수의 순서가 실행 계획에 따라 달라져 맞는 답이 오답이 됩니다. 마지막 정렬 열에 기본 키나 이름처럼 유일한 열을 넣고, 지문에도 정렬 기준을 적으세요. `ORDER BY`가 없는 정답은 만들지 마세요.
- **숫자 표현이 그대로 비교됩니다.** `AVG(정수열)`은 `183.0901`, `10/2`는 `5.0000`, `SUM(DECIMAL)`은 `8510700.00`으로 나옵니다. 학생이 `ROUND`를 쓰거나 안 쓰면 값이 같아도 오답이 됩니다. 지문에 소수 자릿수와 반올림 여부를 명시하고, 정답도 그 형식대로 작성하세요. 날짜는 `DATE`면 `2024-03-23`, `DATETIME`이면 `2024-03-23 00:00:00`입니다.
- 두 테이블에 같은 이름의 열이 있으면 `GROUP BY TEAM.TEAM_ID`처럼 테이블을 붙이세요. `GROUP BY TEAM_ID`는 MySQL이 ambiguous 오류를 냅니다.
- 상관 서브쿼리 안의 `GROUP BY`처럼 느린 형태는 피하세요. 정답 실행 시간이 곧 채점 시간이고 2.5초를 넘으면 문제 자체가 채점 불가가 됩니다.
- 지문의 **예시 출력은 Test 결과를 복사**해서 넣으세요. 그래야 학생이 보는 표현과 일치합니다.

## 차단되는 단어

정답과 학생 쿼리 텍스트에 아래 단어가 **부분 문자열로라도** 들어 있으면 실행 전에 차단됩니다. 대소문자를 구분하지 않고 테이블·열 이름과 문자열 값에도 적용되므로, 스키마를 설계할 때 이 단어가 포함되는 이름을 피하세요.

| 단어 | 걸리는 예 |
|---|---|
| `FILE` | `profile`, `file_name` |
| `EXEC`, `EXECUTE` | `executive`, `execution_date` |
| `SYSTEM`, `SHELL` | `ecosystem`, `system_id`, `seashell` |
| `DELAY`, `SLEEP`, `BENCHMARK`, `HANDLER` | `delayed`, `handler_name` |
| `SYS.`, `SYS_`, `UTL_`, `DBMS_` | `sys_user` |
| `GRANT`, `REVOKE`, `CREATE USER`, `DROP USER`, `ALTER USER`, `SET ROLE` | `grant_amount` |
| `MYSQL.USER`, `INFORMATION_SCHEMA.PROCESSLIST`, `PERFORMANCE_SCHEMA`, `LOAD_FILE`, `INTO OUTFILE`, `LOAD DATA`, `MAX_EXECUTION_TIME` | |

init SQL의 데이터 값에 이런 단어가 있는 것은 괜찮지만, 학생이 그 열을 SELECT하려면 열 이름에 단어가 들어가지 않아야 합니다.

## 출제 전 확인

1. 저장 후 Test로 정답을 실행해 `correct`가 나오는지, 결과 표현이 지문과 같은지 확인합니다.
2. 정렬 기준을 바꾼 대체 정답, 별칭만 다른 정답, `ROUND`를 뺀 정답을 Test해 의도한 것만 통과하는지 확인합니다.
3. 다른 사람이 지문·init·정답·예시 출력을 독립적으로 검토합니다.
4. 문제 세트 전체는 저장소의 `scripts/regrade-challenges`로 한 번에 회귀 검사할 수 있습니다.
