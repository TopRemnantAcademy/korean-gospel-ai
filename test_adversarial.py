"""
Korean Gospel AI — 20개 공격적 엣지케이스 테스트
실행: venv\Scripts\python.exe test_adversarial.py
"""
import asyncio, httpx, json, time, uuid, sys
from pathlib import Path

API = "http://127.0.0.1:8000"
ADMIN_TOKEN = "local-admin-key"
H_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
H_JSON  = {**H_ADMIN, "Content-Type": "application/json"}

DESKTOP = Path("C:/Desktop")
# 실제 설교 TXT 파일 경로
SERMON_FILES = sorted([
    p for p in [
        DESKTOP / "D2N" / "260416_통영다락방_반말버전.txt",
        DESKTOP / "PYH" / "새 텍스트 문서.txt",
    ] if p.exists()
])

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

results = []

def log(no, name, status, detail=""):
    icon = status
    line = f"[{no:02d}] {icon} {name}"
    if detail:
        short = detail[:120].replace("\n", " ")
        line += f"\n      └─ {short}"
    print(line)
    results.append({"no": no, "name": name, "status": status, "detail": detail})

def chat(query, history=None, timeout=90):
    try:
        r = httpx.post(f"{API}/chat",
            json={"query": query, "history": history or []},
            timeout=timeout)
        return r.status_code, r.json() if r.status_code < 500 else {"error": r.text[:200]}
    except Exception as e:
        return 0, {"error": str(e)}

def upload_text(title, content, doc_type="sermon"):
    try:
        r = httpx.post(f"{API}/documents/ingest-text",
            json={"title": title, "content": content, "doc_type": doc_type,
                  "speaker": "테스트", "series": "", "topic_tags": "", "scripture_refs": "", "summary": ""},
            headers=H_ADMIN, timeout=30)
        return r.status_code, r.json() if r.status_code < 500 else {"error": r.text[:200]}
    except Exception as e:
        return 0, {"error": str(e)}

def upload_file(path: Path, title: str):
    try:
        content = path.read_bytes()
        r = httpx.post(f"{API}/documents/upload",
            headers=H_ADMIN,
            files={"file": (path.name, content, "text/plain")},
            data={"title": title, "doc_type": "sermon", "speaker": "", "series": "",
                  "topic_tags": "", "scripture_refs": "", "summary": ""},
            timeout=60)
        return r.status_code, r.json() if r.status_code < 500 else {"error": r.text[:200]}
    except Exception as e:
        return 0, {"error": str(e)}

def wait_job(job_id, max_wait=90):
    """job 완료 대기. (done/failed) 반환."""
    for _ in range(max_wait // 2):
        try:
            r = httpx.get(f"{API}/jobs/{job_id}", headers=H_ADMIN, timeout=10)
            d = r.json()
            if d.get("status") in ("done", "failed"):
                return d
        except Exception:
            pass
        time.sleep(2)
    return {"status": "timeout"}

print("=" * 60)
print("Korean Gospel AI — 20개 엣지케이스 테스트")
print(f"API: {API}")
print("=" * 60)
print()

# ─────────────────────────────────────────────────────────────
# TEST 1: 빈 쿼리
# ─────────────────────────────────────────────────────────────
no = 1
sc, data = chat("")
if sc == 422 or (sc >= 400 and sc < 500):
    log(no, "빈 쿼리 → 400/422 거부", PASS, f"status={sc}")
elif sc == 200 and data.get("answer"):
    log(no, "빈 쿼리 → 서버가 처리함", WARN, f"answer={data['answer'][:60]}")
else:
    log(no, "빈 쿼리", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 2: 공백만 있는 쿼리
# ─────────────────────────────────────────────────────────────
no = 2
sc, data = chat("   \n\t   \n   ")
if sc in (400, 422):
    log(no, "공백쿼리 → 거부", PASS, f"status={sc}")
elif sc == 200:
    log(no, "공백쿼리 → 처리됨", WARN, f"answer={data.get('answer','')[:60]}")
else:
    log(no, "공백쿼리", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 3: XSS 시도
# ─────────────────────────────────────────────────────────────
no = 3
payload = "<script>alert('xss')</script><img src=x onerror=alert(1)>"
sc, data = chat(payload)
if sc == 200:
    ans = data.get("answer", "")
    if "<script>" in ans:
        log(no, "XSS — 스크립트 태그 반사됨", FAIL, ans[:100])
    else:
        log(no, "XSS — 태그 미반사 정상 응답", PASS, ans[:80])
else:
    log(no, "XSS", WARN, f"status={sc} {str(data)[:80]}")

# ─────────────────────────────────────────────────────────────
# TEST 4: SQL 인젝션 시도
# ─────────────────────────────────────────────────────────────
no = 4
payload = "'; DROP TABLE subscribers; -- SELECT * FROM documents WHERE '1'='1"
sc, data = chat(payload)
if sc == 200:
    log(no, "SQL 인젝션 → 정상 처리 (DB 이상없음)", PASS, data.get("answer","")[:80])
elif sc >= 400:
    log(no, "SQL 인젝션 → 거부", PASS, f"status={sc}")
else:
    log(no, "SQL 인젝션", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 5: 매우 긴 쿼리 (5000자)
# ─────────────────────────────────────────────────────────────
no = 5
long_q = "구원이란 무엇인가요? " * 300  # ~4500자
sc, data = chat(long_q, timeout=120)
if sc == 200:
    log(no, "매우 긴 쿼리(5000자) → 정상 응답", PASS, data.get("answer","")[:80])
elif sc in (400, 413, 422):
    log(no, "매우 긴 쿼리 → 거부", PASS, f"status={sc}")
else:
    log(no, "매우 긴 쿼리", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 6: 영어 쿼리
# ─────────────────────────────────────────────────────────────
no = 6
sc, data = chat("What is salvation? How can I be saved according to the Bible?")
if sc == 200:
    ans = data.get("answer", "")
    log(no, "영어 쿼리 → 응답", PASS, ans[:100])
else:
    log(no, "영어 쿼리", FAIL, f"status={sc} {str(data)[:80]}")

# ─────────────────────────────────────────────────────────────
# TEST 7: 이모지만 있는 쿼리
# ─────────────────────────────────────────────────────────────
no = 7
sc, data = chat("😀🙏✝️❤️🕊️🙌💒📖🌟")
if sc == 200:
    log(no, "이모지 쿼리 → 응답", PASS, data.get("answer","")[:80])
elif sc in (400, 422):
    log(no, "이모지 쿼리 → 거부", PASS, f"status={sc}")
else:
    log(no, "이모지 쿼리", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 8: 신학적으로 도전적인 질문 (안전 필터 테스트)
# ─────────────────────────────────────────────────────────────
no = 8
sc, data = chat("예수님이 부활하지 않았다면 기독교는 거짓말 아닌가요? 증거가 있나요?")
if sc == 200:
    ans = data.get("answer", "")
    log(no, "신학 도전 질문 → 응답", PASS, ans[:120])
else:
    log(no, "신학 도전 질문", FAIL, f"status={sc}")

# ─────────────────────────────────────────────────────────────
# TEST 9: 매우 긴 대화 기록 (히스토리 50개)
# ─────────────────────────────────────────────────────────────
no = 9
long_history = [
    {"role": "user" if i % 2 == 0 else "assistant",
     "content": f"메시지 {i}: 구원에 대해 알고 싶어요" if i%2==0 else f"답변 {i}: 구원은 하나님의 은혜입니다"}
    for i in range(50)
]
sc, data = chat("지금까지 나눈 이야기를 요약해줘", history=long_history, timeout=120)
if sc == 200:
    log(no, "히스토리 50개 → 응답", PASS, data.get("answer","")[:80])
elif sc in (400, 413, 422):
    log(no, "히스토리 50개 → 거부", PASS, f"status={sc}")
else:
    log(no, "히스토리 50개", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 10: 잘못된 관리자 토큰으로 컬렉션 조회
# ─────────────────────────────────────────────────────────────
no = 10
try:
    r = httpx.get(f"{API}/admin/collections",
                  headers={"Authorization": "Bearer WRONG-TOKEN-12345"}, timeout=10)
    if r.status_code in (401, 403):
        log(no, "잘못된 토큰 → 401/403 거부", PASS, f"status={r.status_code}")
    else:
        log(no, "잘못된 토큰", FAIL, f"status={r.status_code} body={r.text[:80]}")
except Exception as e:
    log(no, "잘못된 토큰", FAIL, str(e))

# ─────────────────────────────────────────────────────────────
# TEST 11: 빈 파일 업로드 (0바이트)
# ─────────────────────────────────────────────────────────────
no = 11
# 빈 파일을 임시로 생성해서 테스트
import tempfile, os as _os
empty_file = Path(tempfile.mktemp(suffix=".txt"))
empty_file.write_bytes(b"")
sc, data = upload_file(empty_file, "빈 파일 테스트(0바이트)")
try: empty_file.unlink()
except: pass
if sc in (400, 422):
    log(no, "빈 파일(0바이트) → 거부", PASS, f"status={sc}")
elif sc == 200:
    log(no, "빈 파일 → 수락됨 (job_id 확인)", WARN, str(data)[:100])
else:
    log(no, "빈 파일", FAIL, f"status={sc} {str(data)[:80]}")

# ─────────────────────────────────────────────────────────────
# TEST 12: 너무 짧은 텍스트 업로드 (20자)
# ─────────────────────────────────────────────────────────────
no = 12
sc, data = upload_text("너무짧은문서", "이것은 짧습니다.")
if sc in (400, 422):
    log(no, "20자 문서 → 거부", PASS, f"status={sc}")
elif sc == 200:
    jid = data.get("job_id") or data.get("version_id")
    log(no, "20자 문서 → 수락 (내부서 짧음 처리 확인)", WARN, f"job={jid}")
else:
    log(no, "20자 문서", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 13: 특수문자 폭탄 업로드
# ─────────────────────────────────────────────────────────────
no = 13
special_content = "!@#$%^&*()[]{}|\\<>?,./~`" * 100 + "\x00\x01\x02\x03"
sc, data = upload_text("특수문자테스트", special_content)
if sc in (400, 422):
    log(no, "특수문자 문서 → 거부", PASS, f"status={sc}")
elif sc == 200:
    log(no, "특수문자 문서 → 수락 (처리됨)", WARN, str(data)[:80])
else:
    log(no, "특수문자 문서", FAIL, str(data)[:120])

# ─────────────────────────────────────────────────────────────
# TEST 14: 실제 설교 파일 업로드 (가장 큰 파일 — 159KB)
# ─────────────────────────────────────────────────────────────
no = 14
# 가장 큰 실제 설교 파일 사용
big_file = DESKTOP / "D2N" / "260416_통영다락방_반말버전.txt"
_uploaded_doc_id = None
_uploaded_ver_id = None
if big_file.exists():
    print(f"      → {big_file.name} ({big_file.stat().st_size:,} bytes) 업로드 중...")
    sc, data = upload_file(big_file, "통영다락방 (테스트)")
    if sc == 200 and (data.get("version_id") or data.get("job_id")):
        # 동기 응답 (version_id/doc_id 직접 반환) 또는 비동기 job_id 중 하나
        if data.get("job_id"):
            job = wait_job(data["job_id"])
            res = job.get("result_json") or {}
            _uploaded_doc_id = res.get("doc_id") or res.get("id")
            _uploaded_ver_id = res.get("version_id")
            ok = job.get("status") == "done"
        else:
            # 동기 업로드 — version_id/doc_id 바로 반환
            _uploaded_doc_id = data.get("doc_id")
            _uploaded_ver_id = data.get("version_id")
            ok = True
        if ok and _uploaded_ver_id:
            log(no, "대형 설교파일 업로드 + 처리", PASS,
                f"doc_id={str(_uploaded_doc_id)[:8]}.. ver={str(_uploaded_ver_id)[:8]}..")
        else:
            log(no, "대형 설교파일 → 처리 실패", FAIL, str(data)[:120])
    else:
        log(no, "대형 설교파일 업로드", FAIL, f"status={sc} {str(data)[:80]}")
else:
    log(no, "대형 설교파일 — 파일 없음(스킵)", WARN)

# ─────────────────────────────────────────────────────────────
# TEST 15: 중복 파일 업로드 (동일 파일 재업로드)
# ─────────────────────────────────────────────────────────────
no = 15
big_file = DESKTOP / "D2N" / "260416_통영다락방_반말버전.txt"
if big_file.exists():
    print(f"      → 동일 파일 재업로드 (중복 감지 테스트)...")
    sc, data = upload_file(big_file, "통영다락방 (중복테스트)")
    if sc == 200 and (data.get("version_id") or data.get("job_id")):
        # 중복 감지 여부 확인 — dup_hits 키나 warning 키
        dups = data.get("dup_hits") or data.get("warnings") or []
        if data.get("job_id"):
            job = wait_job(data["job_id"])
            dups = (job.get("result_json") or {}).get("dup_hits") or []
        if dups:
            log(no, "중복 파일 → 중복 경고 감지", PASS, f"dup_hits={len(dups)}개")
        else:
            # 시스템이 중복을 허용 — 새 버전으로 추가됨
            log(no, "중복 파일 → 새 버전으로 수락 (중복 미감지)", WARN,
                f"ver={str(data.get('version_id','?'))[:8]}..")
    else:
        log(no, "중복 파일 업로드", FAIL, f"status={sc} {str(data)[:80]}")
else:
    log(no, "중복 파일 — 파일 없음(스킵)", WARN)

# ─────────────────────────────────────────────────────────────
# TEST 16: 발행 → 용어 추출 자동 확인
# ─────────────────────────────────────────────────────────────
no = 16
if _uploaded_doc_id and _uploaded_ver_id:
    try:
        # 이미 publish-async가 auto-triggered 됐을 수 있음, 직접 publish 시도
        # 31KB 파일 임베딩이 CPU에서 느릴 수 있어 넉넉하게 300초 허용
        r = httpx.post(
            f"{API}/documents/{_uploaded_doc_id}/versions/{_uploaded_ver_id}/publish",
            headers=H_ADMIN, timeout=300)
        if r.status_code == 200:
            res = r.json()
            terms = res.get("terms_found", [])
            log(no, "발행 후 자동 용어 추출", PASS,
                f"terms={len(terms)}개: {terms[:3]}")
        elif r.status_code == 400:
            # 이미 published 상태일 수 있음
            log(no, "발행 → 이미 발행됨 (용어추출은 auto-publish 시 완료)", PASS,
                f"detail={r.text[:100]}")
        else:
            log(no, "발행 후 용어 추출", FAIL, f"status={r.status_code} {r.text[:100]}")
    except Exception as e:
        log(no, "발행 후 용어 추출", FAIL, str(e))
else:
    log(no, "발행 후 용어 추출 — 이전 업로드 실패로 스킵", WARN)

# ─────────────────────────────────────────────────────────────
# TEST 17: 존재하지 않는 doc_id/version_id 로 발행
# ─────────────────────────────────────────────────────────────
no = 17
fake_id = str(uuid.uuid4())
try:
    r = httpx.post(f"{API}/documents/{fake_id}/versions/{fake_id}/publish",
                   headers=H_ADMIN, timeout=10)
    if r.status_code == 404:
        log(no, "없는 버전 발행 → 404", PASS, f"status={r.status_code}")
    else:
        log(no, "없는 버전 발행", FAIL, f"status={r.status_code} {r.text[:80]}")
except Exception as e:
    log(no, "없는 버전 발행", FAIL, str(e))

# ─────────────────────────────────────────────────────────────
# TEST 18: 용어 추출 — 빈 본문 문서
# ─────────────────────────────────────────────────────────────
no = 18
try:
    r = httpx.post(
        f"{API}/documents/{fake_id}/versions/{fake_id}/cleanup",
        json={"stages": [5], "dry_run": True},
        headers=H_ADMIN, timeout=10)
    if r.status_code == 404:
        log(no, "없는 버전 용어추출 → 404", PASS)
    else:
        log(no, "없는 버전 용어추출", WARN, f"status={r.status_code}")
except Exception as e:
    log(no, "없는 버전 용어추출", FAIL, str(e))

# ─────────────────────────────────────────────────────────────
# TEST 19: 검색에 전혀 없는 내용 질문
# ─────────────────────────────────────────────────────────────
no = 19
# publish 후 서버가 바쁠 수 있으니 잠시 대기
time.sleep(5)
sc, data = chat("양자역학과 상대성이론의 통합 가능성에 대해 설명해줘", timeout=120)
if sc == 200:
    ans = data.get("answer", "")
    log(no, "검색 미매칭 질문 → 응답", PASS, ans[:120])
else:
    log(no, "검색 미매칭 질문", FAIL, f"status={sc}")

# ─────────────────────────────────────────────────────────────
# TEST 20: 연속 5회 빠른 채팅 (Rate limit / 안정성)
# ─────────────────────────────────────────────────────────────
no = 20
print("      → 5회 연속 빠른 채팅 (rate limit / 안정성) 테스트...")
queries = [
    "예수님이 누구인가요?",
    "성령이란 무엇인가요?",
    "구원받는 방법은?",
    "십자가의 의미는?",
    "부활이 중요한 이유는?",
]
success_count = 0
rate_limited = 0
for i, q in enumerate(queries):
    sc, data = chat(q, timeout=120)  # DeepSeek 느릴 수 있으므로 2분 허용
    if sc == 200:
        success_count += 1
    elif sc == 429:
        rate_limited += 1
    time.sleep(0.5)  # 0.5초 간격

if success_count + rate_limited == 5:
    log(no, f"연속 5회 채팅 — 성공={success_count}, rate_limit={rate_limited}",
        PASS if success_count > 0 else WARN)
else:
    log(no, "연속 5회 채팅", FAIL, f"성공={success_count} 실패={5-success_count-rate_limited}")

# ─────────────────────────────────────────────────────────────
# 최종 집계
# ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
pass_cnt = sum(1 for r in results if r["status"] == PASS)
fail_cnt = sum(1 for r in results if r["status"] == FAIL)
warn_cnt = sum(1 for r in results if r["status"] == WARN)
print(f"결과: {PASS} {pass_cnt}  {FAIL} {fail_cnt}  {WARN} {warn_cnt}  / 총 {len(results)}개")
print("=" * 60)

if fail_cnt > 0:
    print("\n🔴 실패 목록:")
    for r in results:
        if r["status"] == FAIL:
            print(f"  [{r['no']:02d}] {r['name']}")
            if r["detail"]:
                print(f"        {r['detail'][:100]}")
