# SQL 문제 검토 파이프라인

출제된 문제 세트를 배포 전에 한 번에 검사하는 절차입니다. 조교가 직접 실행하거나, 에이전트에게 "문제 검토해 줘"라고 시키면 아래를 그대로 수행합니다. 출제 규칙 자체는 [AUTHORING.md](AUTHORING.md)에 있습니다.

## 필요한 것

- 이 저장소 checkout, Docker, Python 3.12 이상, `curl`, `openssl`
- 검토할 CTFd의 **관리자 access token** (CTFd 로그인 → Settings → Access Tokens). 토큰과 문제 파일은 Git 밖에 둡니다. 이 메타 저장소 관행은 `../private/` 아래입니다.

## 절차

1. **문제 내보내기.** 운영 또는 dev CTFd에서 SQL 문제 정의(지문, init, 정답)를 JSON으로 받습니다.

   ```bash
   CTFD_URL=https://sql.ddps.cloud CTFD_TOKEN=... ./scripts/export-challenges --out ../private/challenges-$(date +%F).json
   ```

   특정 주차만 보려면 `--category Week5`를 붙입니다. DB 덤프에서 만들 때의 SQL은 `scripts/regrade-challenges --help`에 있습니다.

2. **검토 실행.** 일회용 MySQL 8.4과 이 checkout의 judge를 Docker Compose로 띄워 모든 문제를 실제로 채점하고, 끝나면 컨테이너와 volume을 지웁니다.

   ```bash
   ./scripts/review-challenges ../private/challenges-$(date +%F).json --report ../private/review-$(date +%F).json
   ```

   출력의 첫 표는 문제별 상태·소요 시간·행 수이고, `== 검토 결과 ==` 아래에 확인이 필요한 문제와 이유가 나옵니다. 종료 코드가 0이 아니면 실행 실패가 있는 것입니다.

3. **판정 읽기.** 검토 결과의 각 줄은 이렇게 처리합니다.

   | 판정 | 뜻 | 조치 |
   |---|---|---|
   | 실행 실패(`init_error`, `query_error`, `timeout`, `limit`, `blocked`) | 그 문제는 지금 상태로는 채점이 안 됨 | 오류 메시지대로 init 또는 정답을 고친다. AUTHORING.md의 "안 되는 것" 참고 |
   | ORDER BY 없음 / 정렬 키 값이 같은 행 N개 | 맞는 답이 순서 때문에 오답 처리될 수 있음 | 정답의 ORDER BY 마지막에 유일한 열을 추가하고 지문에 정렬 기준을 적는다 |
   | ORDER BY에 식이 있어 자동 확인 불가 | 도구가 동률을 판단하지 못함 | Test 결과를 눈으로 보고 동률이 있으면 위와 같이 처리 |
   | AVG·나눗셈 결과가 ROUND 없이 비교됨 | 학생이 ROUND 유무만 달라도 오답 | 지문에 소수 자릿수를 명시하고 정답을 그 형식으로 맞춘다 |
   | 결과 0행 / 500행 이상 | 의도 확인, 한도 근접 | 데이터나 조건을 조정 |
   | 요청 N ms | 실행당 2.5초 한도에 가까움 | 정답 쿼리를 최적화 |

4. **고친 뒤 다시 실행.** CTFd에서 문제를 수정했으면 1~2를 반복합니다. 검토 결과가 비어 있고 종료 코드가 0이면 끝입니다.

## 다른 엔진과 비교하기

judge 구현이 바뀌었을 때 이전 버전과 결과를 비교하려면 이전 judge를 같은 Compose 네트워크에 띄우고 `--baseline-url`을 넘깁니다. 결과 행이 다른 문제는 `value`, 숫자 표현만 다른 문제는 `numeric_format`으로 분류됩니다.

```bash
./scripts/review-challenges ../private/challenges.json --baseline-url http://old-judge:8080
```

## 이 도구가 보지 못하는 것

- 지문과 정답의 의미가 맞는지, 데이터가 지문과 일치하는지는 사람이 검토해야 합니다. 두 명이 독립적으로 지문·init·정답·예시 출력을 보는 절차를 유지하세요.
- 정렬 키에 `ABS(...)` 같은 식이 있으면 동률을 자동으로 세지 못합니다.
- 학생이 낼 법한 다른 정답이 통과하는지는 Test로 직접 확인해야 합니다.
