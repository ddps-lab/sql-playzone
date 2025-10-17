# Submission Export Plugin

CTFd 플러그인으로 사용자별 제출 현황을 확인하고 CSV로 내보낼 수 있는 기능을 제공합니다.

## 기능

- 모든 사용자의 문제별 제출 현황을 한눈에 확인
- 이름, 이메일, 학번, 문제별 점수를 표시
- CSV 파일로 내보내기 지원
- Admin 패널에서 쉽게 접근 가능

## 설치

이 플러그인은 CTFd의 플러그인 디렉토리에 자동으로 설치됩니다:
```
CTFd/plugins/submission_export/
```

CTFd를 재시작하면 플러그인이 자동으로 로드됩니다.

## 사용 방법

1. Admin 패널에 로그인
2. 상단 메뉴에서 "Submission Export" 클릭
3. 제출 현황 테이블 확인
4. "Export to CSV" 버튼을 클릭하여 CSV 파일 다운로드

## CSV 출력 형식

CSV 파일에는 다음 정보가 포함됩니다:

```
Name, Email, Student ID, Challenge1 (ID: 1), Challenge2 (ID: 2), ...
```

- Name: 사용자 이름
- Email: 사용자 이메일
- Student ID: 학번 (Student ID Number 필드)
- 각 챌린지별 획득 점수 (0 또는 문제 점수)

## 의존성

- CTFd
- student_fields 플러그인 (학번 필드를 위해 필요)

## 특징

- **색상 코딩**:
  - 녹색 배경: 문제 해결 완료
  - 빨간색 배경: 미해결
- **고정 헤더**: 스크롤 시 헤더가 고정되어 편리한 탐색
- **총점 표시**: 각 사용자의 총점이 마지막 열에 표시됨
- **Banned/Hidden 사용자 제외**: 금지되거나 숨겨진 사용자는 표시되지 않음

## 개발자 정보

플러그인 구조:
```
submission_export/
├── __init__.py           # 메인 플러그인 로직
├── templates/
│   └── submission_export.html  # 제출 현황 페이지 템플릿
└── README.md            # 이 문서
```
