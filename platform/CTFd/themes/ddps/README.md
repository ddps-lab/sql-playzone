# DDPS 학생 화면 개발 안내

로그인·설정·SQL 문제 화면에 사용하는 테마입니다. 학생 안내와 시험 설정은 [조교 운영 가이드](../../../../docs/TA_OPERATIONS.md), 코드 테스트는 [개발 가이드](../../../../docs/DEVELOPMENT.md)를 참고해 주세요.

| 경로 | 내용 |
|---|---|
| `templates/` | 서버가 렌더링하는 HTML |
| `assets/` | JavaScript·스타일 소스 |
| `static/` | 브라우저에 배포하는 빌드 결과 |

## SQL 화면을 수정했을 때

저장소 루트에서 테마 의존성을 설치한 뒤 SQL 화면 전용 빌드를 실행할 수 있습니다. Yarn Classic과 Node.js가 필요합니다.

```bash
yarn --cwd platform/CTFd/themes/ddps install --frozen-lockfile
npm --prefix platform/CTFd/themes/ddps run build:sql
node --test tests/js/*.test.cjs
```

`build:sql`은 SQL 페이지·행동 tracker의 정적 파일과 manifest를 갱신합니다. 소스와 빌드 결과를 함께 검토해 commit해야 실제 배포에 반영됩니다. 전체 테마를 수정했다면 이 디렉터리의 `yarn build`를 사용할 수 있으며, 생성된 다른 화면 변경도 확인해야 합니다.

로그인·온보딩·마감·Test·Submit에 영향을 주는 변경은 dev에서 학생 계정으로 확인하는 것이 좋습니다. [제출 점검 가이드](../../plugins/sql_challenges/SUBMISSION_REVIEW.md)를 따라 진행할 수 있습니다.
