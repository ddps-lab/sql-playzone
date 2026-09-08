# 로그인 기록과 학생 풀이 기록 대조

로그인 기록은 `logins.log`에 남고 CloudWatch로 전송됩니다. 운영 환경에서는 서울 리전의 로그 그룹 `/aws/ec2/sql-2026-s2`, 로그 스트림 `logins`에서 조회할 수 있습니다. 개발 환경의 그룹은 `/aws/ec2/sql-2026-s2-dev`입니다. 조회에는 해당 환경의 AWS 로그 조회 권한이 필요합니다.

## 기록에 포함되는 계정 정보

```text
[09/08/2026 12:00:00] 192.0.2.1 - event=session_started user_id=42 login_id="student42" "김민수" session started via form ("Trustlockbrowser/2.1.1"); first session on record
```

- `user_id`: 플랫폼 계정의 고유 번호입니다. 동명이인, 표시 이름 변경, 로그인 ID 변경 후에도 같은 계정의 기록을 연결할 수 있습니다.
- `login_id`: 로그인 시점에 설정된 플랫폼 로그인 ID입니다. 이메일로 로그인해도 계정에 저장된 ID가 기록됩니다. Google 첫 가입처럼 아직 ID를 설정하지 않은 경우에는 `null`로 남으며 `user_id`로 조회할 수 있습니다.
- `event=session_started`: 가입·일반 로그인·Google 로그인 등으로 새 로그인 세션이 시작됐음을 나타냅니다. 직전 로그인과의 시간 간격·IP·브라우저도 함께 기록합니다.
- 일반·Google 로그인 성공 시 남는 기본 로그에는 `event=login_success`와 같은 계정 식별자가 포함됩니다. 로그인 횟수를 셀 때에는 `session_started` 기록 한 종류를 사용하면 됩니다.

식별자는 로그인한 계정에서 가져옵니다. 이름과 브라우저 문자열은 따옴표·개행을 이스케이프해 한 로그 항목 안에 기록합니다.

## 학생 한 명의 로그인 조회

1. 플랫폼 관리자 **Users**에서 이름·학번·이메일로 학생을 확인하고 계정 고유 번호를 확인합니다. 사용자 상세 주소 `/admin/users/42`의 `42`가 `user_id`입니다.
2. CloudWatch **Logs Insights**에서 해당 환경의 애플리케이션 로그 그룹과 시험 시간 범위를 선택합니다.
3. 다음 쿼리의 `42`를 학생의 고유 번호로 바꿔 실행합니다.

```text
fields @timestamp, @message
| filter @logStream = "logins"
| parse @message /^\[[^\]]+\] \S+ - event=(?<login_event>[a-z_]+) user_id=(?<account_id>[0-9]+) login_id=/
| filter login_event = "session_started" and account_id = "42"
| sort @timestamp asc
```

쿼리는 로그 앞부분의 이벤트와 고유 번호를 사용하므로 이름이 같거나 이름에 검색어가 포함돼도 해당 학생의 로그인만 고를 수 있습니다. [CloudWatch의 parse 문법](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-Parse.html)을 사용합니다.

## Test·행동·제출 기록과 연결

Test와 브라우저 행동은 행동 로그 그룹 `/aws/ec2/sql-2026-s2-behavior`에 기록되며 각 이벤트의 `user_id`가 로그인 로그와 같습니다. 개발 환경에서는 `/aws/ec2/sql-2026-s2-dev-behavior`를 사용합니다.

학생·문제 번호와 시험 시간 범위로 Test(`event_type=execute`) 및 입력·붙여넣기·창 전환 이벤트를 추리고, 관리자 **Submissions**(`/admin/submissions`)의 제출 SQL·시각·판정과 대조할 수 있습니다. 학번과의 연결은 관리자 Users에서 확인하면 됩니다.

새 식별자는 이 변경이 포함된 버전을 배포한 뒤 생성되는 로그인부터 기록됩니다. 이전 형식의 로그에는 고유 번호가 없으므로 동일한 번호 기반 조회를 적용할 수 없습니다.
