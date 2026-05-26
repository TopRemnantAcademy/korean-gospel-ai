# 🧪 베타 → 테스트 → 출시 워크플로우

사용자가 향후 진행할 방향: **메인 코드는 그대로 두고, 베타 사본을 별도로 만들어 거기서 수정/테스트 후 출시**.

---

## 권장 폴더 구조

```
C:\Desktop\
├── korean-gospel-ai\          ← 메인 (지금 폴더, 안정 운영)
├── korean-gospel-ai-beta\     ← 베타 (복사본, 실험)
└── korean-gospel-ai-release\  ← 출시본 (베타에서 검증된 것만)
```

---

## 단계별 흐름

### 1. 메인이 안정되면 베타 사본 만들기 (1회)

PowerShell:
```powershell
Copy-Item -Path "C:\Desktop\korean-gospel-ai" -Destination "C:\Desktop\korean-gospel-ai-beta" -Recurse -Exclude @("venv",".qdrant_local",".gospel.db","data\uploads")
```
- venv, DB, 업로드 캐시는 제외 → 베타에서 새로 만듦
- 베타 폴더에서 `STEP1_INSTALL.bat` 다시 실행

### 2. 베타에서 실험

베타 폴더에서만:
- 코드 수정
- 새 기능 추가
- 깨도 됨

베타 포트를 다르게 하고 싶으면 `STEP3_START.bat`의 `8000` `8501` 을 `8002` `8503` 등으로 변경.

### 3. 베타 검증 완료 → 출시본으로 승격

```powershell
# 옛 출시본 백업
Rename-Item "C:\Desktop\korean-gospel-ai-release" "korean-gospel-ai-release.bak"
# 베타를 출시본으로
Copy-Item "C:\Desktop\korean-gospel-ai-beta" "C:\Desktop\korean-gospel-ai-release" -Recurse -Exclude @("venv",".qdrant_local",".gospel.db","data\uploads")
```
출시본 폴더에서 `STEP1` 다시.

---

## 데이터는?

- **DB(`.gospel.db`)**: 환경마다 별도. 베타 데이터와 출시 데이터 섞이지 않음.
- **업로드 파일(`data/uploads`)**: 별도. 베타에서 테스트 업로드해도 출시본에 영향 없음.
- **벡터 DB(`.qdrant_local`)**: 별도.
- **원본 자료(`data/documents`)**: 공통으로 둬도 됨 (읽기 전용).

---

## 코드 동기화

가장 단순한 방법: **Git 사용** (강력 추천)
```bash
cd C:\Desktop\korean-gospel-ai
git init
git add . && git commit -m "main stable"
git branch beta            # 베타 브랜치
git checkout beta          # 베타에서 작업
# 검증 끝나면
git checkout main && git merge beta
```
이러면 폴더 복사 없이 한 폴더 안에서 메인/베타 전환 가능.

Git 어렵다면 위의 폴더 복사 방식이 가장 단순.

---

## 지금 단계

현재 폴더(`korean-gospel-ai`)는 아직 **MVP 검증 단계**. 안정적으로 동작하기 시작하면 위 베타 분리를 시작하세요. 무리하게 지금 분리할 필요 없음.
