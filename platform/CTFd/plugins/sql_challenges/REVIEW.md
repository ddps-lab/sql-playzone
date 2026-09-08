# 문제 세트 검토 가이드

여러 SQL 문제를 게시하기 전에 한 번에 실행해 보는 절차입니다. 서비스에서 문제 정의를 파일로 내보내고, 내 컴퓨터의 임시 MySQL 8.4에서 정답 SQL을 실행해 문제별 오류·결과 크기·소요 시간을 확인할 수 있습니다.

처음 만드는 문제는 [출제 가이드](AUTHORING.md)의 예제로 관리자 화면을 먼저 익혀 주세요. Docker나 관리자 토큰을 준비하기 어렵다면 개발 담당자에게 검사 실행을 요청하고 조교는 보고서의 지문·정답 검토를 맡을 수 있습니다.

## 1. 준비할 것

| 준비물 | 확인 방법 |
|---|---|
| 서비스 주소와 관리자 계정 | 운영 담당자에게 검사할 환경을 확인해 주세요. |
| 이 저장소의 소스 | [저장소 내려받기](../../../../README.md)를 참고해 주세요. 운영 담당자가 지정한 검사 버전으로 준비해야 합니다. |
| Git, Python 3.12 이상, Docker와 Compose v2, curl, openssl, realpath | Linux 또는 WSL의 Bash 터미널을 기준으로 아래 명령을 실행할 수 있습니다. Docker도 실행 중이어야 합니다. |
| 비공개 작업 디렉터리 | 문제 파일에는 정답이 들어 있으므로 Git 저장소 밖에 보관해야 합니다. |

**저장소 루트**에서 도구를 확인해 주세요. `platform`, `scripts`, `IaC`가 보이는 디렉터리입니다.

```bash
git --version
python3 --version
docker compose version
docker info > /dev/null
curl --version
openssl version
command -v realpath
```

## 2. 관리자 토큰과 작업 디렉터리 준비

검사할 서비스에 관리자로 로그인한 뒤 **Settings → Access Tokens**에서 토큰을 생성해 주세요. API 토큰은 명령행 도구가 관리자 대신 문제를 조회할 때 쓰는 인증 값입니다. 검사 후 필요가 없어진 토큰은 같은 화면에서 삭제할 수 있습니다.

다음 명령은 **Bash**에서 실행해 주세요. 서비스 주소는 실제 대상 주소로 바꾸고, 토큰 입력 요청이 나오면 생성한 토큰을 붙여 넣으면 됩니다. 토큰은 화면에 표시되지 않습니다.

```bash
umask 077
review_dir=$(mktemp -d "${TMPDIR:-/tmp}/sql-problem-review.XXXXXX")
export CTFD_URL='https://sql-dev.ddps.cloud'
read -r -s -p '관리자 토큰: ' CTFD_TOKEN
export CTFD_TOKEN
```

`review_dir`는 이번 검사 파일을 보관할 임시 디렉터리입니다. 보고서를 오래 보관하려면 검사 후 수업의 비공개 저장소로 옮겨야 합니다.

## 3. 문제 정의 내보내기

```bash
./scripts/export-challenges --out "$review_dir/challenges.json"
unset CTFD_TOKEN
```

`N SQL challenges written to ...`가 출력되면 내보내기가 끝난 것입니다. N이 예상 문제 수와 맞는지 확인해 주세요. 특정 Category만 받으려면 내보내기 명령에 `--category 'Week5'`처럼 실제 분류명을 추가하면 됩니다.

파일에는 지문, 초기화 SQL, 정답 SQL, 채점 기준 등이 들어갑니다. 학생 계정의 토큰을 사용하면 필요한 문제 정의를 받을 수 없으므로 관리자 계정인지 확인해야 합니다. 다시 내보낼 때는 2단계처럼 토큰을 입력해야 합니다.

## 4. 일괄 실행

같은 Bash 터미널·저장소 루트에서 다음을 실행해 주세요.

```bash
./scripts/review-challenges "$review_dir/challenges.json" \
  --report "$review_dir/report.json"
```

첫 실행에는 Docker 이미지 다운로드·빌드로 수 분이 걸릴 수 있습니다. 스크립트는 현재 소스의 채점 서버(judge)와 임시 MySQL을 띄우고, 문제마다 정답 SQL을 실행·비교한 뒤 전용 컨테이너와 볼륨을 정리합니다.

기본 검사 포트는 18080입니다. 이미 사용 중이면 다음처럼 바꿀 수 있습니다.

```bash
SQL_JUDGE_REVIEW_PORT=18081 ./scripts/review-challenges \
  "$review_dir/challenges.json" --report "$review_dir/report.json"
```

Docker 검토 서비스는 선택한 포트를 호스트에 공개합니다. 정답이 포함된 검토는 접근을 통제할 수 있는 개인 컴퓨터나 연구실 개발 서버에서 진행해야 합니다.

## 5. 결과를 읽고 수정하기

처음 표의 `status`는 실행 상태, `ms`는 요청 소요 시간, `rows`는 결과 행 수, `bytes`는 응답 크기입니다. 이어 나오는 **검토 결과**에서 확인할 문제와 이유를 볼 수 있습니다.

| 표시 | 뜻 | 다음 조치 |
|---|---|---|
| `ok` | 정답 SQL을 정상 실행하고 자기 자신과의 비교를 통과함 | 지문·대체 정답을 사람이 검토해야 합니다. |
| `policy_required` | 공개 채점 기준이 미확정 | 관리자 문제 수정 화면에서 정렬·표시 형식 기준을 저장해야 합니다. |
| `init_error`, `query_error` | 초기화 또는 정답 SQL 실행 실패 | 표시된 오류를 관리자 Test에서 확인하고 SQL을 수정해 주세요. |
| `timeout`, `limit`, `blocked` | 시간·크기·허용 SQL 범위 문제 | [출제 가이드](AUTHORING.md)의 실행 한도를 확인하고 데이터·쿼리를 조정해야 합니다. |
| `busy`, `http_error`, `transport_error` | 검사 서버가 혼잡하거나 연결·응답 실패 | Docker 상태와 로그를 확인한 뒤 다시 실행해 주세요. |
| 정답 결과 0행 | 조건에 맞는 데이터가 없음 | 의도한 빈 결과인지 지문·데이터를 확인해야 합니다. |
| 500행 이상, 느린 요청 | 결과 크기·실행 시간이 한도에 가까움 | 데이터 규모와 정답 SQL을 검토하는 것이 좋습니다. 느린 요청의 기본 표시 기준은 1,500ms입니다. |

종료 코드가 0이면 실행 오류 검사는 통과한 것입니다. **0행·느린 요청 같은 검토 알림은 종료 코드 0에서도 나올 수 있으므로 검토 결과를 함께 읽어야 합니다.** 문제를 수정했다면 다시 내보내기부터 실행해 주세요. 내보낸 JSON은 그 시점의 문제 사본입니다.

검토가 끝나면 서비스, 소스 commit(`git rev-parse HEAD`), 날짜, 예상·실제 문제 수, 수정·재검사 결과와 지문을 검토한 조교를 기록하는 것이 좋습니다.

## 실행 중 막혔을 때

| 증상 | 확인할 것 |
|---|---|
| `No such file` 또는 명령을 찾지 못함 | 저장소 루트인지, 1단계 도구가 준비됐는지 확인해 주세요. |
| HTTP 401·403 | 서비스 주소와 관리자 토큰의 권한·유효 기간을 확인해야 합니다. |
| 내보낸 문제가 0개 | 해당 서비스에 SQL 문제가 있는지, Category 이름이 정확한지 확인해 주세요. |
| Docker 연결 실패 | Docker 실행 상태와 현재 사용자의 Docker 권한을 확인해야 합니다. |
| 포트 사용 중 | `SQL_JUDGE_REVIEW_PORT`로 비어 있는 포트를 지정할 수 있습니다. |
| 이미지 빌드·MySQL 기동 실패 | 오류 메시지와 Docker 상태를 개발 담당자에게 전달해 주세요. 토큰과 비공개 문제 내용은 제외해야 합니다. |

검사 결과를 수정한 뒤에는 [제출 점검 가이드](SUBMISSION_REVIEW.md)로 학생 화면의 Test·Submit·성적 반영을 확인할 수 있습니다. 서로 다른 채점 엔진의 결과 비교나 자동 테스트 추가는 [개발 가이드](../../../../docs/DEVELOPMENT.md)를 참고해 주세요.
