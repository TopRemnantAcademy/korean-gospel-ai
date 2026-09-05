"""환경 진단 도구.
모든 핵심 의존성을 import 시도하고, 어디서 막히는지 찾아낸다.
실행: python scripts/diagnose.py
"""
from __future__ import annotations
import os
import sys
import socket
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 출력은 stdout + 파일 양쪽
LOG_FILE = ROOT / "diagnose_result.txt"
log_lines = []


def out(s=""):
    print(s)
    log_lines.append(s)


def check(name, fn):
    try:
        result = fn()
        msg = f"  [OK]   {name}"
        if result:
            msg += f"  ({result})"
        out(msg)
        return True
    except Exception as e:
        out(f"  [FAIL] {name}")
        out(f"         -> {type(e).__name__}: {e}")
        return False


def main():
    out("=" * 70)
    out("   RAG - DIAGNOSE")
    out("=" * 70)

    out(f"\nPython     : {sys.version.split()[0]}  ({sys.executable})")
    out(f"Workdir    : {Path.cwd()}")
    out(f"Root dir   : {ROOT}")

    # ---- .env ----
    out("\n[1] .env file")
    env_path = ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        out(f"  [OK]   .env loaded")
        if os.getenv("GOOGLE_API_KEY"):
            out(f"  [OK]   GOOGLE_API_KEY is set ({len(os.getenv('GOOGLE_API_KEY'))} chars)")
        else:
            out(f"  [FAIL] GOOGLE_API_KEY is EMPTY")
    else:
        out(f"  [FAIL] .env not found at {env_path}")

    # ---- Core packages ----
    out("\n[2] Core packages (must all be OK)")
    pkgs = [
        ("fastapi",      lambda: __import__("fastapi").__version__),
        ("uvicorn",      lambda: __import__("uvicorn").__version__),
        ("pydantic",     lambda: __import__("pydantic").VERSION),
        ("httpx",        lambda: __import__("httpx").__version__),
        ("dotenv",       lambda: __import__("dotenv").__name__),
        ("yaml",         lambda: __import__("yaml").__name__),
        ("numpy",        lambda: __import__("numpy").__version__),
        ("pandas",       lambda: __import__("pandas").__version__),
        ("streamlit",    lambda: __import__("streamlit").__version__),
    ]
    for name, fn in pkgs:
        check(name, fn)

    # ---- RAG packages ----
    out("\n[3] RAG packages (some may take a moment first time)")
    rag = [
        ("qdrant_client",         lambda: __import__("qdrant_client").__name__),
        ("sentence_transformers", lambda: __import__("sentence_transformers").__name__),
        ("transformers",          lambda: __import__("transformers").__version__),
        ("torch",                 lambda: __import__("torch").__version__),
        ("fastembed",             lambda: __import__("fastembed").__name__),
        ("kss",                   lambda: __import__("kss").__name__),
        ("pypdf",                 lambda: __import__("pypdf").__name__),
        ("sqlalchemy",            lambda: __import__("sqlalchemy").__version__),
        ("alembic",               lambda: __import__("alembic").__version__),
    ]
    for name, fn in rag:
        check(name, fn)

    # ---- LLM SDK ----
    out("\n[4] LLM SDK")
    check("google.genai", lambda: __import__("google.genai", fromlist=["Client"]).__name__)
    check("langfuse",     lambda: __import__("langfuse").__name__)

    # ---- Port 8000 ----
    out("\n[5] Port 8000 (uvicorn's port)")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", 8000))
        s.close()
        if result == 0:
            out("  [WARN] Port 8000 already in use by something. "
                "Either uvicorn is already running, or another app uses it.")
        else:
            out("  [OK]   Port 8000 is FREE (uvicorn can start here)")
    except Exception as e:
        out(f"  [FAIL] port check error: {e}")

    # ---- FastAPI app load ----
    out("\n[6] FastAPI app full import (the most critical test)")
    sys.path.insert(0, str(ROOT))
    try:
        from backend.app.main import app  # noqa: F401
        out("  [OK]   backend.app.main:app loaded successfully")
    except Exception:
        out("  [FAIL] FastAPI app failed to load!")
        out("  ---- Traceback ----")
        for line in traceback.format_exc().splitlines():
            out("  " + line)
        out("  -------------------")

    # ---- Save ----
    out("\n" + "=" * 70)
    LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")
    out(f"  Full report saved to:  {LOG_FILE}")
    out("=" * 70)


if __name__ == "__main__":
    main()
