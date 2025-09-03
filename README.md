# SQL PlayZone - SQL 학습 플랫폼

SQL PlayZone은 CTFd 프레임워크를 기반으로 구축된 SQL 학습 및 문제 풀이 플랫폼입니다. 사용자가 SQL 쿼리 문제를 풀면서 데이터베이스 조작 능력을 향상시킬 수 있도록 설계되었습니다.

## 프로젝트 개요

이 프로젝트는 CTFd (Capture The Flag 프레임워크)를 커스터마이징하여 SQL 문제 풀이 기능을 추가한 교육용 플랫폼입니다. 

### 주요 기능

- **SQL 문제 풀이**: 사용자가 SQL 쿼리를 작성하고 실행하여 문제를 해결
- **자동 채점 시스템**: Go 기반의 MySQL 서버를 통한 실시간 쿼리 검증
- **다양한 문제 유형 지원**: 기본 CTF 문제와 SQL 특화 문제 모두 지원
- **팀/개인 경쟁**: 개인 또는 팀 단위로 참여 가능
- **실시간 순위표**: 점수 및 진행 상황 실시간 확인
- **관리자 인터페이스**: 문제 생성 및 관리를 위한 웹 기반 관리자 도구

## 시스템 구성

### 핵심 컴포넌트

1. **CTFd 웹 애플리케이션** (Python/Flask)
   - 사용자 인터페이스
   - 문제 관리 및 채점
   - 사용자 인증 및 권한 관리

2. **SQL Judge Server** (Go)
   - SQL 쿼리 실행 및 검증
   - 안전한 샌드박스 환경 제공
   - MySQL 호환 쿼리 처리

3. **데이터베이스** (MariaDB)
   - 플랫폼 데이터 저장
   - 사용자, 문제, 점수 관리

4. **캐시 서버** (Redis)
   - 세션 관리
   - 성능 최적화

5. **웹 서버** (Nginx)
   - 리버스 프록시
   - 정적 파일 서빙

## 설치 및 실행 방법

### 사전 요구 사항

- Docker 및 Docker Compose
- Git
- 최소 4GB RAM
- 10GB 이상의 디스크 공간

### 빠른 시작 (Docker Compose 사용)

1. **저장소 클론**
   ```bash
   git clone [repository-url]
   cd sql-playzone/platform
   ```

2. **CTFd 설정 파일 생성**
   ```bash
   # config.ini 파일 생성 (필수)
   cp CTFd/config.example.ini CTFd/config.ini
   ```

3. **Docker Compose로 실행**
   ```bash
   docker compose up -d
   ```

4. **웹 브라우저에서 접속**
   - http://localhost (Nginx를 통한 접속)
   - http://localhost:8000 (CTFd 직접 접속)

5. **초기 설정**
   - 첫 접속 시 관리자 계정 생성
   - 플랫폼 기본 설정 구성
   - SQL 문제 생성 및 배포

### 개발 환경 설정 (로컬 실행)

1. **Python 가상 환경 설정**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 또는
   venv\Scripts\activate  # Windows
   ```

2. **의존성 설치**
   ```bash
   pip install -r requirements.txt
   ```

3. **데이터베이스 설정**
   - MariaDB 설치 및 실행
   - Redis 설치 및 실행
   - 환경 변수 설정:
     ```bash
     export DATABASE_URL=mysql+pymysql://ctfd:ctfd@localhost/ctfd
     export REDIS_URL=redis://localhost:6379
     ```

4. **SQL Judge Server 빌드 및 실행**
   ```bash
   cd CTFd/plugins/sql_challenges
   go mod tidy
   go build -o sql-judge-server sql_judge_server.go
   ./sql-judge-server
   ```

5. **CTFd 실행**
   ```bash
   python serve.py
   # 또는
   flask run --host=0.0.0.0 --port=8000
   ```

## 환경 변수 설정

모든 환경 변수는 `docker-compose.yml` 파일에 정의되어 있습니다. 필요시 이 파일을 직접 수정하세요.

### docker-compose.yml에서 환경 변수 수정하기

```yaml
services:
  ctfd:
    environment:
      - DATABASE_URL=mysql+pymysql://ctfd:ctfd@db/ctfd  # DB 연결 정보
      - REDIS_URL=redis://cache:6379                     # Redis 캐시
      - SQL_JUDGE_SERVER_URL=http://sql-judge:8080       # SQL 판정 서버
      # 필요시 아래 값들을 수정하세요
      - WORKERS=1
      - REVERSE_PROXY=true
```

### 주요 환경 변수 설명

#### CTFd 서비스
| 환경 변수 | 설명 | 기본값 |
|----------|------|--------|
| `DATABASE_URL` | 데이터베이스 연결 문자열 | `mysql+pymysql://ctfd:ctfd@db/ctfd` |
| `REDIS_URL` | Redis 캐시 서버 URL | `redis://cache:6379` |
| `SQL_JUDGE_SERVER_URL` | SQL 판정 서버 URL | `http://sql-judge:8080` |
| `UPLOAD_FOLDER` | 파일 업로드 디렉토리 | `/var/uploads` |
| `LOG_FOLDER` | 로그 파일 디렉토리 | `/var/log/CTFd` |
| `WORKERS` | 워커 프로세스 수 | `1` |
| `REVERSE_PROXY` | 리버스 프록시 사용 여부 | `true` |

#### MariaDB 서비스
| 환경 변수 | 설명 | 기본값 |
|----------|------|--------|
| `MARIADB_ROOT_PASSWORD` | root 비밀번호 | `ctfd` |
| `MARIADB_USER` | 데이터베이스 사용자명 | `ctfd` |
| `MARIADB_PASSWORD` | 데이터베이스 비밀번호 | `ctfd` |
| `MARIADB_DATABASE` | 데이터베이스명 | `ctfd` |

### 보안 주의사항

**프로덕션 환경에서는 반드시 다음 값들을 변경하세요:**
- 데이터베이스 비밀번호 (`MARIADB_PASSWORD`, `MARIADB_ROOT_PASSWORD`)
- CTFd SECRET_KEY (CTFd/config.ini 파일에서 설정)

### 포트 변경

포트를 변경하려면 `docker-compose.yml`의 `ports` 섹션을 수정하세요:
```yaml
services:
  nginx:
    ports:
      - "80:80"     # 웹 서버 포트 (변경: "8080:80")
  ctfd:
    ports:
      - "8000:8000" # CTFd 직접 접속 포트
```

## SQL 문제 만들기

### 관리자 패널에서 문제 생성

1. 관리자로 로그인
2. Admin Panel → Challenges → Create Challenge
3. Challenge Type으로 "sql" 선택
4. 다음 필드 입력:
   - **Name**: 문제 제목
   - **Category**: 문제 카테고리
   - **Description**: 문제 설명
   - **Init Query**: 테이블 생성 및 데이터 삽입 SQL
   - **Solution Query**: 정답 SQL 쿼리
   - **Value**: 문제 점수

### Init Query 예시
```sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(50),
    age INT,
    city VARCHAR(50)
);

INSERT INTO users VALUES 
(1, 'Alice', 25, 'Seoul'),
(2, 'Bob', 30, 'Busan'),
(3, 'Charlie', 35, 'Daegu');
```

### Solution Query 예시
```sql
SELECT name, age FROM users WHERE city = 'Seoul';
```

## 프로젝트 구조

```
platform/
├── CTFd/                      # CTFd 핵심 코드
│   ├── plugins/               # 플러그인 디렉토리
│   │   └── sql_challenges/    # SQL 문제 플러그인
│   │       ├── __init__.py    # 플러그인 메인 로직
│   │       ├── sql_judge_server.go  # Go 판정 서버
│   │       └── assets/        # 프론트엔드 리소스
│   ├── themes/                # UI 테마
│   ├── models/                # 데이터베이스 모델
│   └── api/                   # REST API
├── docker-compose.yml         # Docker 구성
├── Dockerfile                 # CTFd 이미지 빌드
├── requirements.txt           # Python 의존성
└── serve.py                   # 개발 서버 실행 스크립트
```

## 문제 해결

### 일반적인 문제

1. **포트 충돌**
   - 80, 8000, 3306, 6379 포트가 사용 중인지 확인
   - docker-compose.yml에서 포트 매핑 수정

2. **데이터베이스 연결 오류**
   - MariaDB 서비스 실행 확인
   - DATABASE_URL 환경 변수 확인
   - 방화벽 설정 확인

3. **SQL Judge Server 오류**
   - Go가 설치되어 있는지 확인
   - 8080 포트가 사용 가능한지 확인
   - SQL_JUDGE_SERVER_URL 환경 변수 확인

### 로그 확인

```bash
# Docker 로그 확인
docker compose logs -f ctfd
docker compose logs -f sql-judge
docker compose logs -f db

# 로컬 실행 시 로그 위치
.data/CTFd/logs/
```

## 개발 및 커스터마이징

### 새로운 문제 유형 추가

1. `CTFd/plugins/` 디렉토리에 새 플러그인 생성
2. `BaseChallenge` 클래스 상속
3. 필요한 메서드 구현 (create, read, update, delete, attempt)

### 테마 커스터마이징

1. `CTFd/themes/` 디렉토리에서 기존 테마 복사
2. HTML, CSS, JavaScript 수정
3. 관리자 패널에서 새 테마 선택

## 보안 고려사항

- SQL 쿼리는 격리된 환경에서 실행
- 사용자 입력은 모두 검증 및 살균 처리
- CSRF 토큰으로 보호
- Rate limiting 적용
- SSL/TLS 사용 권장 (프로덕션 환경)

## 라이센스

이 프로젝트는 CTFd의 Apache License 2.0을 따릅니다.

## 기여하기

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

## 지원

문제가 있거나 도움이 필요한 경우:
- GitHub Issues 생성
- 프로젝트 위키 참조
- 커뮤니티 포럼 참여