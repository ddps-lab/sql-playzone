# SQL Playzone

SQL Playzone은 SQL 수업의 문제 풀이·시험·성적 확인에 사용하는 서비스입니다. 학생은 SQL을 작성해 **Test**로 실행 결과를 확인하고 **Submit**으로 성적을 제출할 수 있습니다. 조교는 관리자 화면에서 문제, 학생 계정, 시험 참여 규칙과 성적을 관리할 수 있습니다.

## 처음 맡은 조교라면

운영 담당자에게 **서비스 주소, 관리자 계정, 연습할 개발 환경(dev) 주소**를 먼저 받아 주세요. 출제와 시험 운영은 웹 관리자 화면에서 시작할 수 있습니다.

| 하려는 일 | 읽을 문서 | 준비물 |
|---|---|---|
| 학생 가입 안내·시험 명단·브라우저 제한 설정 | [조교 운영 가이드](docs/TA_OPERATIONS.md) | 관리자 계정, 수강생 명단 |
| SQL 문제 만들기 | [출제 가이드](platform/CTFd/plugins/sql_challenges/AUTHORING.md) | 지문, 테이블·데이터, 정답 SQL |
| 여러 문제를 게시 전에 검사하기 | [문제 검토 가이드](platform/CTFd/plugins/sql_challenges/REVIEW.md) | 관리자 계정, Git·Docker·Python을 사용할 컴퓨터 |
| 학생 입장에서 실행·제출·성적을 확인하기 | [제출 점검 가이드](platform/CTFd/plugins/sql_challenges/SUBMISSION_REVIEW.md) | dev 관리자 계정, 테스트용 학생 계정 |
| 성적 CSV 내려받기 | [성적 내보내기 가이드](platform/CTFd/plugins/submission_export/README.md) | 관리자 계정, 수강생 명단 |
| 시험 전에 서버 수를 확보하기 | [AWS 운영 가이드](IaC/README.md) | AWS·Terraform 담당자와 시험 일정 |
| 서비스 업데이트·이전 버전 복원 | [배포 가이드](IaC/ARTIFACT_PIPELINE.md) | 배포 권한과 대상 환경 설정 |
| 코드 수정·자동 테스트 실행 | [개발 가이드](docs/DEVELOPMENT.md) | 소스와 개발 도구 |

권장 순서는 **운영 가이드 → 예제 문제 만들기 → 학생 계정으로 제출 점검 → 실제 문제 세트 검토**입니다. AWS 자원을 만드는 작업이 필요하면 배포 담당자와 환경·비용·적용 시점을 확인해야 합니다.

## 서비스 구성

| 구성 요소 | 역할 |
|---|---|
| CTFd | 웹 애플리케이션입니다. 계정, 문제, 제출 기록과 점수를 관리합니다. |
| SQL judge | Go로 작성한 채점 서버입니다. 정답과 학생 SQL을 MySQL 8.4에서 실행하고 결과를 비교합니다. |
| 채점용 MySQL | 문제 데이터를 요청마다 임시 DB에 준비합니다. 정답과 학생 SQL은 같은 데이터를 각각의 읽기 전용 연결에서 조회합니다. |
| Aurora MySQL | AWS 배포에서 계정·문제·성적 등 서비스 데이터를 보관합니다. |
| Valkey | AWS 배포에서 캐시와 로그인 세션을 공유합니다. |
| Nginx·ALB | 웹 요청을 전달하고 서버 상태를 확인합니다. ALB는 AWS의 로드 밸런서입니다. |
| S3 | AWS 배포에서 문제 첨부 파일과 로그를 보관합니다. |

## 저장소 내려받기

문서를 웹으로 읽거나 관리자 화면을 사용하는 데는 소스 설치가 필요하지 않습니다. 문제 일괄 검사나 개발 작업을 하려면 다음과 같이 소스를 받을 수 있습니다.

```bash
git clone https://github.com/ddps-lab/sql-playzone.git
cd sql-playzone
```

이 디렉터리를 각 가이드에서 **저장소 루트**라고 부릅니다. `README.md`, `platform`, `scripts`, `IaC`가 보이면 맞는 위치입니다. 검사·개발에 사용할 브랜치나 commit은 운영 담당자에게 확인해 주세요.

| 경로 | 내용 |
|---|---|
| `platform/CTFd/plugins/sql_challenges/` | SQL 문제·채점 코드와 출제 가이드 |
| `platform/CTFd/plugins/` | 계정 설정, 시험 규칙, 성적 내보내기 기능 |
| `platform/CTFd/themes/ddps/` | 학생 화면 |
| `scripts/` | 문제 검사와 배포 명령 |
| `IaC/` | AWS 인프라·배포 설정 |
| `docs/` | 조교 운영·개발 안내 |

문제·정답 파일, 학생 정보, 관리자 토큰과 비밀번호는 접근이 제한된 경로에 보관해야 합니다. 개발 점검에는 테스트용 계정과 예제 문제를 사용해 주세요.

이 프로젝트는 CTFd를 기반으로 하며 Apache License 2.0을 따릅니다. CTFd 원본 설명은 [platform/README.md](platform/README.md)에 있습니다.
