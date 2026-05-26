"""업그레이드 전 공통 Pre-flight 체크."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    description: str
    passed: bool
    error: str = ""


def check_command_exists(cmd: str, description: str) -> Check:
    path = shutil.which(cmd)
    if path:
        return Check(name=cmd, description=description, passed=True)
    return Check(name=cmd, description=description, passed=False,
                 error=f"'{cmd}' 명령어를 찾을 수 없습니다. 설치 후 다시 시도하세요.")


def check_env_var(var: str, description: str) -> Check:
    val = os.getenv(var, "")
    if val.strip():
        return Check(name=var, description=description, passed=True)
    return Check(name=var, description=description, passed=False,
                 error=f"환경변수 {var} 가 비어 있습니다. .env 파일을 확인하세요.")


def check_file_exists(path: str, description: str) -> Check:
    if os.path.exists(path):
        return Check(name=path, description=description, passed=True)
    return Check(name=path, description=description, passed=False,
                 error=f"파일이 없습니다: {path}")


def check_python_package(pkg: str, description: str) -> Check:
    try:
        __import__(pkg)
        return Check(name=pkg, description=description, passed=True)
    except ImportError:
        return Check(name=pkg, description=description, passed=False,
                     error=f"Python 패키지 '{pkg}' 가 설치되어 있지 않습니다. pip install {pkg}")


def check_network_reachable(host: str, description: str) -> Check:
    import socket
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, 443))
        return Check(name=host, description=description, passed=True)
    except Exception as e:
        return Check(name=host, description=description, passed=False,
                     error=f"네트워크 연결 실패: {e}")


def check_db_accessible(db_path: str = ".gospel.db") -> Check:
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return Check(name="sqlite_db", description="SQLite DB 접근 가능", passed=True)
    except Exception as e:
        return Check(name="sqlite_db", description="SQLite DB 접근 가능", passed=False,
                     error=str(e))


# Tier별 pre-flight 체크 묶음

def preflight_tier_0_to_0_5() -> list[Check]:
    return [
        check_network_reachable("cloudflare.com", "Cloudflare 서버 접근"),
        check_file_exists(".env", ".env 파일 존재"),
        check_db_accessible(),
    ]


def preflight_tier_0_5_to_1() -> list[Check]:
    return [
        check_command_exists("fly", "Fly.io CLI 설치 여부"),
        check_command_exists("docker", "Docker 설치 여부"),
        check_file_exists("Dockerfile", "Dockerfile 존재"),
        check_file_exists(".env", ".env 파일 존재"),
        check_network_reachable("fly.io", "Fly.io 서버 접근"),
    ]


def preflight_tier_1_to_1_5() -> list[Check]:
    return [
        check_env_var("SUPABASE_URL", "Supabase URL 설정"),
        check_env_var("SUPABASE_SERVICE_KEY", "Supabase Service Key 설정"),
        check_env_var("QDRANT_URL", "Qdrant Cloud URL 설정"),
        check_env_var("QDRANT_API_KEY", "Qdrant Cloud API Key 설정"),
        check_db_accessible(),
    ]


def preflight_tier_1_5_to_2() -> list[Check]:
    return [
        check_env_var("SUPABASE_URL", "Supabase URL 설정"),
        check_env_var("SUPABASE_SERVICE_KEY", "Supabase Service Key 설정"),
        check_env_var("QDRANT_URL", "Qdrant Cloud URL 설정"),
        check_env_var("QDRANT_API_KEY", "Qdrant Cloud API Key 설정"),
        check_python_package("psycopg2", "psycopg2 설치 (Postgres 연결용)"),
        check_network_reachable("supabase.co", "Supabase 서버 접근"),
        check_db_accessible(),
    ]
