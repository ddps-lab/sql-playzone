# 공개 약관과 개인정보처리방침 관리

방문자는 로그인하지 않고 `/tos`에서 서비스 이용약관을, `/privacy`에서 개인정보처리방침을 읽을 수 있습니다. 메인 페이지 하단의 두 링크에서도 같은 문서로 이동합니다.

## 본문 수정

1. 관리자로 로그인한 뒤 **Config → Legal**을 엽니다.
2. **Terms of Service** 탭의 본문을 수정하면 `/tos`에 반영됩니다.
3. **Privacy Policy** 탭의 본문을 수정하면 `/privacy`에 반영됩니다.
4. 자체 페이지를 사용할 때에는 각 탭의 URL 입력란을 비워 두고 저장해야 합니다. URL을 입력하면 해당 외부 주소로 이동합니다.
5. 로그아웃한 브라우저에서 두 주소와 메인 페이지 하단의 링크를 확인해 주세요.

플러그인은 본문과 URL이 모두 비어 있는 항목에만 `terms.md` 또는 `privacy.md`를 처음 등록합니다. 이미 등록된 본문은 재배포해도 유지되므로, 파일을 수정한 뒤 기존 사이트에도 반영하려면 위 화면에서 본문을 갱신해야 합니다. 데이터 가져오기로 설정이 교체된 경우에도 본문을 확인해 주세요.

## 운영자가 본문 확정 전에 확인할 내용

현재 본문은 기존 약관의 보관·문의 기준을 이어받았습니다. 다음 항목은 실제 수업 운영 방침을 확인해 구체화해야 합니다.

- 개인정보 처리 주체와 담당 연락처: 수업에 참여하기 전인 방문자도 연락할 수 있는 이메일을 기재해 주세요.
- 계정, 답안, 행동 기록, 접속 로그의 보유 기간과 삭제 절차: DB 백업·로그 보관본까지 포함해 정해야 합니다. CloudWatch 행동 로그의 3일 보존 설정만으로 전체 기록의 보관 기간을 판단하면 안 됩니다.
- 교육 연구 이용 범위, 별도 동의와 IRB 검토 필요 여부: 담당 연구자와 확인해 본문과 실제 운영을 일치시켜 주세요.
- AWS·Google·Microsoft 이용 계약과 데이터 처리 설정: 위탁·제공·국외 이전에 필요한 고지와 분석 서비스별 보관 기간을 확인해 주세요. 현재 테마에는 Google Analytics와 Microsoft Clarity가 포함되어 있습니다.

## Google 애플리케이션 설정에 입력할 주소

| 항목 | 운영 주소 |
| --- | --- |
| 애플리케이션 홈페이지 | `https://sql.ddps.cloud/` |
| 개인정보처리방침 | `https://sql.ddps.cloud/privacy` |
| 서비스 약관 | `https://sql.ddps.cloud/tos` |

운영 DNS와 서버를 배포해 실제로 접속할 수 있게 된 뒤 입력해야 합니다. dev에서는 호스트를 `sql-dev.ddps.cloud`로 바꾸어 확인할 수 있습니다.

참고: [Google OAuth 공개 홈페이지 요구사항](https://developers.google.com/identity/protocols/oauth2/policies), [Microsoft Clarity 고지 안내](https://learn.microsoft.com/en-us/clarity/setup-and-installation/privacy-disclosure).
