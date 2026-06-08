"""⚙️ 설정 — API 키·모델·기능 플래그 전체 관리."""
from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="설정", page_icon="⚙️", layout="wide")
st.title("⚙️ 설정")
st.caption("모든 설정 변경은 .env 파일에 저장됩니다. 저장 후 **백엔드를 재시작**해야 적용돼요.")

ENV_PATH = _ROOT / ".env"

# ─────────────────────────────────────────────────────────────────────────────
# .env 파일 읽기 / 쓰기 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _read_env() -> tuple[dict[str, str], str]:
    """Returns (key→value dict, raw text)."""
    if not ENV_PATH.exists():
        return {}, ""
    raw = ENV_PATH.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, val = stripped.partition("=")
            val = val.strip().strip('"').strip("'")
            result[key.strip().upper()] = val
    return result, raw


def _write_env(updates: dict[str, str]):
    """Write updates back to .env, preserving comments and ordering."""
    _, raw = _read_env()
    lines = raw.splitlines() if raw else []
    written: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip().upper()
            if key in updates:
                val = updates[key]
                # Quote values that contain spaces or are empty
                if " " in val or (val == "" and key in updates):
                    new_lines.append(f'{key}="{val}"')
                else:
                    new_lines.append(f"{key}={val}")
                written.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Append any new keys not already in the file
    for key, val in updates.items():
        if key not in written:
            if " " in val:
                new_lines.append(f'{key}="{val}"')
            else:
                new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 현재 .env 로드
# ─────────────────────────────────────────────────────────────────────────────
env, _raw = _read_env()

def _g(key: str, default: str = "") -> str:
    return env.get(key.upper(), default)

def _gb(key: str, default: bool = False) -> bool:
    v = _g(key).lower()
    return v in ("1", "true", "yes") if v else default

def _gi(key: str, default: int = 0) -> int:
    try:
        return int(_g(key) or default)
    except ValueError:
        return default

def _gf(key: str, default: float = 0.0) -> float:
    try:
        return float(_g(key) or default)
    except ValueError:
        return default


# 현재 백엔드에 로드된 값 확인
from admin.lib.api_client import get_health
import httpx
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "local-admin-key")

def _get_live_settings():
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/admin/settings",
                      headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 탭
# ─────────────────────────────────────────────────────────────────────────────
tab_llm, tab_emb, tab_ret, tab_auth, tab_feat, tab_quota, tab_lf, tab_raw = st.tabs([
    "🤖 LLM", "🧮 임베딩·검색", "🔍 검색 파라미터",
    "🔐 인증·보안", "🚦 기능 플래그", "🎫 쿼터", "📡 Langfuse", "📄 Raw .env",
])

all_updates: dict[str, str] = {}  # accumulated across all tabs


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: LLM
# ─────────────────────────────────────────────────────────────────────────────
with tab_llm:
    st.subheader("LLM 설정")
    with st.form("form_llm"):
        provider = st.selectbox(
            "기본 LLM Provider",
            ["gemini", "openai", "claude", "ollama", "deepseek"],
            index=["gemini", "openai", "claude", "ollama", "deepseek"].index(_g("LLM_PROVIDER", "gemini"))
            if _g("LLM_PROVIDER", "gemini") in ["gemini", "openai", "claude", "ollama", "deepseek"] else 0,
        )
        c1, c2 = st.columns(2)
        with c1:
            fb_enabled = st.checkbox("Fallback 활성화", value=_gb("LLM_FALLBACK_ENABLED", True))
        with c2:
            fb_chain = st.text_input("Fallback 순서 (CSV)", value=_g("LLM_FALLBACK_CHAIN"),
                                     placeholder="openai,claude,deepseek")

        st.divider()
        st.markdown("#### Gemini")
        g1, g2 = st.columns(2)
        with g1:
            google_key = st.text_input("GOOGLE_API_KEY", value=_g("GOOGLE_API_KEY"),
                                       type="password", placeholder="AIza...")
        with g2:
            gemini_model = st.text_input("GEMINI_MODEL", value=_g("GEMINI_MODEL", "gemini-2.5-flash"))

        st.markdown("#### OpenAI")
        o1, o2 = st.columns(2)
        with o1:
            openai_key = st.text_input("OPENAI_API_KEY", value=_g("OPENAI_API_KEY"),
                                       type="password", placeholder="sk-...")
        with o2:
            openai_model = st.text_input("OPENAI_MODEL", value=_g("OPENAI_MODEL", "gpt-4o-mini"))

        st.markdown("#### Claude (Anthropic)")
        cl1, cl2 = st.columns(2)
        with cl1:
            anthropic_key = st.text_input("ANTHROPIC_API_KEY", value=_g("ANTHROPIC_API_KEY"),
                                          type="password", placeholder="sk-ant-...")
        with cl2:
            claude_model = st.text_input("CLAUDE_MODEL", value=_g("CLAUDE_MODEL", "claude-sonnet-4-6"))

        st.markdown("#### Ollama (로컬)")
        ol1, ol2 = st.columns(2)
        with ol1:
            ollama_host = st.text_input("OLLAMA_HOST", value=_g("OLLAMA_HOST", "http://localhost:11434"))
        with ol2:
            ollama_model = st.text_input("OLLAMA_MODEL", value=_g("OLLAMA_MODEL", "qwen2.5:7b"))

        st.markdown("#### DeepSeek")
        ds1, ds2, ds3 = st.columns(3)
        with ds1:
            deepseek_key = st.text_input("DEEPSEEK_API_KEY", value=_g("DEEPSEEK_API_KEY"),
                                         type="password")
        with ds2:
            deepseek_model = st.text_input("DEEPSEEK_MODEL", value=_g("DEEPSEEK_MODEL", "deepseek-chat"))
        with ds3:
            deepseek_url = st.text_input("DEEPSEEK_BASE_URL", value=_g("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))

        if st.form_submit_button("💾 LLM 설정 저장", type="primary", use_container_width=True):
            updates = {
                "LLM_PROVIDER": provider,
                "LLM_FALLBACK_ENABLED": "true" if fb_enabled else "false",
                "LLM_FALLBACK_CHAIN": fb_chain,
                "GOOGLE_API_KEY": google_key,
                "GEMINI_MODEL": gemini_model,
                "OPENAI_API_KEY": openai_key,
                "OPENAI_MODEL": openai_model,
                "ANTHROPIC_API_KEY": anthropic_key,
                "CLAUDE_MODEL": claude_model,
                "OLLAMA_HOST": ollama_host,
                "OLLAMA_MODEL": ollama_model,
                "DEEPSEEK_API_KEY": deepseek_key,
                "DEEPSEEK_MODEL": deepseek_model,
                "DEEPSEEK_BASE_URL": deepseek_url,
            }
            _write_env(updates)
            st.success("✅ LLM 설정 저장 완료 — 백엔드를 재시작해야 적용돼요")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: 임베딩 & 재랭커
# ─────────────────────────────────────────────────────────────────────────────
with tab_emb:
    st.subheader("임베딩 & 재랭커 설정")
    with st.form("form_emb"):
        e1, e2 = st.columns(2)
        with e1:
            embedder_opts = ["kure", "bge_m3", "e5", "hf_inference", "voyage"]
            emb_val = _g("EMBEDDER", "kure")
            embedder = st.selectbox(
                "기본 임베더",
                embedder_opts,
                index=embedder_opts.index(emb_val) if emb_val in embedder_opts else 0,
            )
        with e2:
            embedder_list = st.text_input("임베더 목록 (CSV)", value=_g("EMBEDDER_LIST", "kure,bge_m3"),
                                          help="여러 임베더로 멀티-인덱스 구성 시")

        hf_token = st.text_input("HF_TOKEN (Hugging Face)", value=_g("HF_TOKEN"),
                                 type="password", placeholder="hf_...")
        voyage_key = st.text_input("VOYAGE_API_KEY", value=_g("VOYAGE_API_KEY"), type="password")

        st.divider()
        r1, r2 = st.columns(2)
        with r1:
            reranker_opts = ["bge_m3", "cohere", "none"]
            rer_val = _g("RERANKER", "bge_m3")
            reranker = st.selectbox(
                "재랭커",
                reranker_opts,
                index=reranker_opts.index(rer_val) if rer_val in reranker_opts else 0,
            )
        with r2:
            cohere_key = st.text_input("COHERE_API_KEY", value=_g("COHERE_API_KEY"), type="password")

        if st.form_submit_button("💾 임베딩 설정 저장", type="primary", use_container_width=True):
            _write_env({
                "EMBEDDER": embedder,
                "EMBEDDER_LIST": embedder_list,
                "HF_TOKEN": hf_token,
                "VOYAGE_API_KEY": voyage_key,
                "RERANKER": reranker,
                "COHERE_API_KEY": cohere_key,
            })
            st.success("✅ 임베딩 설정 저장 완료 — 백엔드를 재시작해야 적용돼요")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 3: 검색 파라미터 + 벡터 DB
# ─────────────────────────────────────────────────────────────────────────────
with tab_ret:
    st.subheader("검색 파라미터 & 벡터 DB")
    with st.form("form_ret"):
        st.markdown("#### 검색 가중치")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            top_k = st.number_input("RETRIEVAL_TOP_K", 1, 100, _gi("RETRIEVAL_TOP_K", 20))
        with p2:
            rerank_n = st.number_input("RERANK_TOP_N", 1, 50, _gi("RERANK_TOP_N", 5))
        with p3:
            dense_w = st.slider("DENSE_WEIGHT", 0.0, 1.0, _gf("DENSE_WEIGHT", 0.7), 0.05)
        with p4:
            sparse_w = st.slider("SPARSE_WEIGHT", 0.0, 1.0, _gf("SPARSE_WEIGHT", 0.3), 0.05)

        st.markdown("#### Qdrant 벡터 DB")
        q1, q2 = st.columns(2)
        with q1:
            qdrant_url = st.text_input("QDRANT_URL", value=_g("QDRANT_URL", "http://localhost:6333"))
            qdrant_key = st.text_input("QDRANT_API_KEY", value=_g("QDRANT_API_KEY"), type="password",
                                       help="로컬 Qdrant는 불필요")
        with q2:
            qdrant_prefix = st.text_input("QDRANT_COLLECTION_PREFIX", value=_g("QDRANT_COLLECTION_PREFIX", "gospel"))
            sparse_enabled = st.checkbox("QDRANT_SPARSE_ENABLED (하이브리드 검색)",
                                         value=_gb("QDRANT_SPARSE_ENABLED", True))

        if st.form_submit_button("💾 검색 설정 저장", type="primary", use_container_width=True):
            _write_env({
                "RETRIEVAL_TOP_K": str(top_k),
                "RERANK_TOP_N": str(rerank_n),
                "DENSE_WEIGHT": str(dense_w),
                "SPARSE_WEIGHT": str(sparse_w),
                "QDRANT_URL": qdrant_url,
                "QDRANT_API_KEY": qdrant_key,
                "QDRANT_COLLECTION_PREFIX": qdrant_prefix,
                "QDRANT_SPARSE_ENABLED": "true" if sparse_enabled else "false",
            })
            st.success("✅ 검색 설정 저장 완료")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 4: 인증 & 보안
# ─────────────────────────────────────────────────────────────────────────────
with tab_auth:
    st.subheader("인증 & 보안 설정")
    st.warning("⚠️ 이 설정은 민감해요. 변경 후 반드시 백엔드를 재시작하세요.")
    with st.form("form_auth"):
        a1, a2 = st.columns(2)
        with a1:
            app_pw = st.text_input("APP_PASSWORD (관리자 화면 비밀번호)", value=_g("APP_PASSWORD"),
                                   type="password", help="이 화면 접근 비밀번호")
            admin_key = st.text_input("ADMIN_API_KEY (백엔드 Admin API 키)", value=_g("ADMIN_API_KEY"),
                                      type="password", placeholder="change-me 에서 변경 필수")
        with a2:
            dify_key = st.text_input("DIFY_API_KEY", value=_g("DIFY_API_KEY"), type="password")
            cors = st.text_input("CORS_ORIGINS (콤마 구분)",
                                 value=_g("CORS_ORIGINS", "http://localhost:8501"),
                                 help="허용할 Origin. 프로덕션에서 도메인으로 교체")

        if st.form_submit_button("💾 인증 설정 저장", type="primary", use_container_width=True):
            _write_env({
                "APP_PASSWORD": app_pw,
                "ADMIN_API_KEY": admin_key,
                "DIFY_API_KEY": dify_key,
                "CORS_ORIGINS": cors,
            })
            st.success("✅ 인증 설정 저장 완료 — 반드시 백엔드를 재시작하세요")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 5: 기능 플래그
# ─────────────────────────────────────────────────────────────────────────────
with tab_feat:
    st.subheader("기능 플래그 (Feature Flags)")
    st.caption("각 기능을 ON/OFF할 수 있어요. 개발·시범 운영 시 일부를 끄면 도움이 돼요.")
    with st.form("form_feat"):
        f1, f2 = st.columns(2)
        with f1:
            policy_on       = st.checkbox("POLICY_ENABLED (안전정책 필터)",              value=_gb("POLICY_ENABLED", True))
            salv_det        = st.checkbox("SALVATION_DETECTION_ENABLED (구원 신호 감지)", value=_gb("SALVATION_DETECTION_ENABLED", True))
            salv_prompt     = st.checkbox("SALVATION_PROMPT_ENABLED (구원 상태별 프롬프트)", value=_gb("SALVATION_PROMPT_ENABLED", True))
            legalism        = st.checkbox("LEGALISM_CHECK_ENABLED (율법주의 차단)",       value=_gb("LEGALISM_CHECK_ENABLED", True))
        with f2:
            ret_boost       = st.checkbox("RETRIEVER_BOOST_ENABLED (구원·다락방 부스트)", value=_gb("RETRIEVER_BOOST_ENABLED", True))
            gospel_fallback = st.checkbox("GOSPEL_CORE_FALLBACK_ENABLED (검색 0건 복음 핵심 노출)", value=_gb("GOSPEL_CORE_FALLBACK_ENABLED", True))
            token_quota     = st.checkbox("TOKEN_QUOTA_ENABLED (토큰 쿼터 적용)",         value=_gb("TOKEN_QUOTA_ENABLED", True))
            rate_limit      = st.checkbox("RATE_LIMIT_ENABLED (Rate Limit 적용)",         value=_gb("RATE_LIMIT_ENABLED", True))

        log_level = st.selectbox("LOG_LEVEL", ["INFO", "DEBUG", "WARNING", "ERROR"],
                                 index=["INFO", "DEBUG", "WARNING", "ERROR"].index(_g("LOG_LEVEL", "INFO"))
                                 if _g("LOG_LEVEL", "INFO") in ["INFO", "DEBUG", "WARNING", "ERROR"] else 0)
        data_dir = st.text_input("DATA_DIR (자료 저장 경로)", value=_g("DATA_DIR", "data/documents"))

        if st.form_submit_button("💾 기능 플래그 저장", type="primary", use_container_width=True):
            _write_env({
                "POLICY_ENABLED":               "true" if policy_on else "false",
                "SALVATION_DETECTION_ENABLED":  "true" if salv_det else "false",
                "SALVATION_PROMPT_ENABLED":     "true" if salv_prompt else "false",
                "LEGALISM_CHECK_ENABLED":       "true" if legalism else "false",
                "RETRIEVER_BOOST_ENABLED":      "true" if ret_boost else "false",
                "GOSPEL_CORE_FALLBACK_ENABLED": "true" if gospel_fallback else "false",
                "TOKEN_QUOTA_ENABLED":          "true" if token_quota else "false",
                "RATE_LIMIT_ENABLED":           "true" if rate_limit else "false",
                "LOG_LEVEL":                    log_level,
                "DATA_DIR":                     data_dir,
            })
            st.success("✅ 기능 플래그 저장 완료")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 6: 쿼터 (무료체험 / 토큰)
# ─────────────────────────────────────────────────────────────────────────────
with tab_quota:
    st.subheader("토큰 쿼터 & 무료체험 설정")
    with st.form("form_quota"):
        q1, q2 = st.columns(2)
        with q1:
            t_guest   = st.number_input("TOKENS_DAILY_GUEST (게스트 일일 무료 토큰)", 0, 100000, _gi("TOKENS_DAILY_GUEST", 5000))
            t_member  = st.number_input("TOKENS_MONTHLY_MEMBER (유료회원 월간 토큰)", 0, 10000000, _gi("TOKENS_MONTHLY_MEMBER", 100000), step=10000)
        with q2:
            t_support = st.number_input("TOKENS_MONTHLY_SUPPORTER (후원회원 월간 토큰)", 0, 10000000, _gi("TOKENS_MONTHLY_SUPPORTER", 500000), step=10000)
            t_est     = st.number_input("TOKEN_ESTIMATE_PER_REQUEST (요청당 사전 차감 견적)", 100, 10000, _gi("TOKEN_ESTIMATE_PER_REQUEST", 2000))

        st.divider()
        st.markdown("#### 무료체험 (rate_limit.py 상수)")
        st.info("아래 값들은 `backend/app/middleware/rate_limit.py` 상수입니다. 저장 후 코드도 직접 반영돼요.")
        rl1, rl2, rl3 = st.columns(3)
        with rl1:
            trial_days = st.number_input("FREE_TRIAL_DAYS (무료 체험 기간, 일)", 1, 30, 3)
        with rl2:
            trial_3h_limit = st.number_input("FREE_TRIAL_3H_LIMIT (3시간당 쿼리 한도)", 1, 100, 10)
        with rl3:
            st.caption("적용: 체험 기간 동안 3시간마다 리셋")

        if st.form_submit_button("💾 쿼터 설정 저장", type="primary", use_container_width=True):
            # .env 업데이트
            _write_env({
                "TOKENS_DAILY_GUEST":        str(t_guest),
                "TOKENS_MONTHLY_MEMBER":     str(t_member),
                "TOKENS_MONTHLY_SUPPORTER":  str(t_support),
                "TOKEN_ESTIMATE_PER_REQUEST": str(t_est),
            })
            # rate_limit.py 상수 직접 수정
            rl_path = _ROOT / "backend" / "app" / "middleware" / "rate_limit.py"
            if rl_path.exists():
                rl_text = rl_path.read_text(encoding="utf-8")
                import re
                rl_text = re.sub(r"FREE_TRIAL_DAYS\s*=\s*\d+",    f"FREE_TRIAL_DAYS = {trial_days}", rl_text)
                rl_text = re.sub(r"FREE_TRIAL_3H_LIMIT\s*=\s*\d+", f"FREE_TRIAL_3H_LIMIT = {trial_3h_limit}", rl_text)
                rl_path.write_text(rl_text, encoding="utf-8")
                st.success(f"✅ 쿼터 저장 완료 (rate_limit.py: 체험 {trial_days}일, {trial_3h_limit}회/3h)")
            else:
                st.success("✅ .env 쿼터 저장 완료 (rate_limit.py 파일 없음)")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 7: Langfuse
# ─────────────────────────────────────────────────────────────────────────────
with tab_lf:
    st.subheader("Langfuse 관측성 설정")
    st.caption("Langfuse는 LLM 호출 추적·비용 분석 도구입니다. https://cloud.langfuse.com")
    with st.form("form_lf"):
        lf_enabled = st.checkbox("LANGFUSE_ENABLED", value=_gb("LANGFUSE_ENABLED", True))
        lf1, lf2 = st.columns(2)
        with lf1:
            lf_pub = st.text_input("LANGFUSE_PUBLIC_KEY", value=_g("LANGFUSE_PUBLIC_KEY"),
                                   type="password", placeholder="pk-lf-...")
            lf_sec = st.text_input("LANGFUSE_SECRET_KEY", value=_g("LANGFUSE_SECRET_KEY"),
                                   type="password", placeholder="sk-lf-...")
        with lf2:
            lf_host = st.text_input("LANGFUSE_HOST", value=_g("LANGFUSE_HOST", "https://cloud.langfuse.com"))

        if st.form_submit_button("💾 Langfuse 설정 저장", type="primary", use_container_width=True):
            _write_env({
                "LANGFUSE_ENABLED":    "true" if lf_enabled else "false",
                "LANGFUSE_PUBLIC_KEY": lf_pub,
                "LANGFUSE_SECRET_KEY": lf_sec,
                "LANGFUSE_HOST":       lf_host,
            })
            st.success("✅ Langfuse 설정 저장 완료")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 8: Raw .env 보기 + 현재 백엔드 로드 값
# ─────────────────────────────────────────────────────────────────────────────
with tab_raw:
    col_raw, col_live = st.columns(2)

    with col_raw:
        st.subheader("📄 .env 파일 원문")
        if ENV_PATH.exists():
            # 비밀번호/API 키 마스킹해서 표시
            masked_lines = []
            for line in _raw.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, val = stripped.partition("=")
                    key_upper = key.strip().upper()
                    is_secret = any(k in key_upper for k in ["KEY", "SECRET", "PASSWORD", "TOKEN"])
                    if is_secret and val.strip():
                        v = val.strip().strip('"').strip("'")
                        masked = f"****{v[-4:]}" if len(v) > 6 else "****"
                        masked_lines.append(f"{key.strip()}={masked}")
                    else:
                        masked_lines.append(line)
                else:
                    masked_lines.append(line)
            st.code("\n".join(masked_lines), language="bash")
        else:
            st.warning(f".env 파일을 찾을 수 없어요: {ENV_PATH}")

    with col_live:
        st.subheader("🔴 현재 백엔드 로드 값")
        st.caption("백엔드가 실제로 사용 중인 값 (재시작 전 .env 저장과 다를 수 있어요)")
        live = _get_live_settings()
        if live:
            for section, vals in live.items():
                with st.expander(section.upper()):
                    for k, v in vals.items():
                        color = "#4CAF50" if v and v != "(없음)" and v != "None" else "#888"
                        v_str = str(v) if v is not None else "—"
                        st.markdown(
                            f"<code style='color:{color}'>{k}</code> = <code>{v_str}</code>",
                            unsafe_allow_html=True,
                        )
        else:
            st.warning("백엔드 연결 실패 — 서버가 실행 중인지 확인하세요")
