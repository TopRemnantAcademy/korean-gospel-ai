"""Tier 0 → Tier 0.5: Cloudflare Tunnel 설정."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

from .base import UpgradeRunner, UpgradeProgress, register_upgrade
from .checks import preflight_tier_0_to_0_5, Check
from .rollback import full_snapshot, full_restore


@register_upgrade
class Tier0To05(UpgradeRunner):
    name = "tier_0_to_0_5"
    estimated_minutes = 10
    requires_consent = True
    rollback_window_hours = 24

    async def preflight(self) -> list[Check]:
        return preflight_tier_0_to_0_5()

    async def backup(self) -> str:
        return full_snapshot()

    async def execute(self, progress_cb: Callable | None = None):
        steps = [
            ("cloudflared 설치 확인", self._check_cloudflared),
            ("config.yml 확인", self._check_config),
            ("STEP4_TUNNEL.bat 확인", self._check_bat),
            ("CURRENT_TIER 환경변수 업데이트", self._update_tier_env),
        ]
        for i, (label, fn) in enumerate(steps):
            if progress_cb:
                pct = int((i / len(steps)) * 100)
                await progress_cb(UpgradeProgress(i + 1, len(steps), label, pct))
            fn()

    def _check_cloudflared(self):
        import shutil
        if not shutil.which("cloudflared"):
            print("⚠️  cloudflared 가 PATH 에 없습니다.")
            print("   scripts/install_cloudflared.bat 을 먼저 실행하세요.")

    def _check_config(self):
        if not os.path.exists("config.yml"):
            print("⚠️  config.yml 이 없습니다. 프로젝트 루트에 생성하세요.")
        else:
            print("✅ config.yml 존재")

    def _check_bat(self):
        if not os.path.exists("STEP4_TUNNEL.bat"):
            print("⚠️  STEP4_TUNNEL.bat 이 없습니다.")
        else:
            print("✅ STEP4_TUNNEL.bat 존재")

    def _update_tier_env(self):
        _update_env_key("CURRENT_TIER", "tier_0_5")
        print("✅ CURRENT_TIER=tier_0_5 설정됨")

    async def verify(self) -> bool:
        return os.path.exists("config.yml") and os.path.exists("STEP4_TUNNEL.bat")

    async def rollback(self, snapshot_id: str):
        full_restore(snapshot_id)
        _update_env_key("CURRENT_TIER", "tier_0")
        print("↩️  Tier 0 으로 롤백 완료")


@register_upgrade
class Tier05To1(UpgradeRunner):
    name = "tier_0_5_to_1"
    estimated_minutes = 30
    requires_consent = True
    rollback_window_hours = 24

    async def preflight(self) -> list[Check]:
        from .checks import preflight_tier_0_5_to_1
        return preflight_tier_0_5_to_1()

    async def backup(self) -> str:
        return full_snapshot()

    async def execute(self, progress_cb: Callable | None = None):
        steps = [
            ("fly.io 로그인 확인", self._check_fly_auth),
            ("fly.toml 확인", self._check_fly_toml),
            ("Dockerfile 확인", self._check_dockerfile),
            ("CURRENT_TIER 업데이트", self._update_tier_env),
        ]
        for i, (label, fn) in enumerate(steps):
            if progress_cb:
                await progress_cb(UpgradeProgress(i + 1, len(steps), label, int(i / len(steps) * 100)))
            fn()

    def _check_fly_auth(self):
        import shutil
        if not shutil.which("fly") and not shutil.which("flyctl"):
            print("⚠️  fly CLI 가 없습니다. https://fly.io/docs/hands-on/install-flyctl/")
            return
        result = subprocess.run(["fly", "auth", "whoami"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ fly.io 로그인됨: {result.stdout.strip()}")
        else:
            print("⚠️  fly.io 로그인 필요: fly auth login")

    def _check_fly_toml(self):
        if os.path.exists("fly.toml"):
            print("✅ fly.toml 존재")
        else:
            print("⚠️  fly.toml 없음 — fly launch 로 생성하세요")

    def _check_dockerfile(self):
        if os.path.exists("Dockerfile"):
            print("✅ Dockerfile 존재")
        else:
            print("❌ Dockerfile 없음!")

    def _update_tier_env(self):
        _update_env_key("CURRENT_TIER", "tier_1")
        print("✅ CURRENT_TIER=tier_1 설정됨")

    async def verify(self) -> bool:
        return os.path.exists("fly.toml") and os.path.exists("Dockerfile")

    async def rollback(self, snapshot_id: str):
        full_restore(snapshot_id)
        _update_env_key("CURRENT_TIER", "tier_0_5")
        print("↩️  Tier 0.5 으로 롤백 완료")


@register_upgrade
class Tier1To15(UpgradeRunner):
    name = "tier_1_to_1_5"
    estimated_minutes = 60
    requires_consent = True
    rollback_window_hours = 48

    async def preflight(self) -> list[Check]:
        from .checks import preflight_tier_1_to_1_5
        return preflight_tier_1_to_1_5()

    async def backup(self) -> str:
        return full_snapshot()

    async def execute(self, progress_cb: Callable | None = None):
        steps = [
            ("Supabase 연결 확인", self._check_supabase),
            ("Qdrant Cloud 연결 확인", self._check_qdrant),
            ("CURRENT_TIER 업데이트", self._update_tier_env),
        ]
        for i, (label, fn) in enumerate(steps):
            if progress_cb:
                await progress_cb(UpgradeProgress(i + 1, len(steps), label, int(i / len(steps) * 100)))
            fn()

    def _check_supabase(self):
        url = os.getenv("SUPABASE_URL", "")
        if url:
            print(f"✅ SUPABASE_URL 설정됨")
        else:
            print("⚠️  SUPABASE_URL 없음 — .env 에 추가하세요")

    def _check_qdrant(self):
        url = os.getenv("QDRANT_URL", "")
        key = os.getenv("QDRANT_API_KEY", "")
        if url and key:
            print("✅ Qdrant Cloud 환경변수 설정됨")
        else:
            print("⚠️  QDRANT_URL / QDRANT_API_KEY 없음 — .env 에 추가하세요")

    def _update_tier_env(self):
        _update_env_key("CURRENT_TIER", "tier_1_5")
        print("✅ CURRENT_TIER=tier_1_5 설정됨")

    async def verify(self) -> bool:
        return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("QDRANT_URL"))

    async def rollback(self, snapshot_id: str):
        full_restore(snapshot_id)
        _update_env_key("CURRENT_TIER", "tier_1")
        print("↩️  Tier 1 으로 롤백 완료")


@register_upgrade
class Tier15To2(UpgradeRunner):
    """SQLite → Supabase PostgreSQL + Qdrant Cloud 마이그레이션."""
    name = "tier_1_5_to_2"
    estimated_minutes = 120
    requires_consent = True
    rollback_window_hours = 72

    async def preflight(self) -> list[Check]:
        from .checks import preflight_tier_1_5_to_2
        return preflight_tier_1_5_to_2()

    async def backup(self) -> str:
        return full_snapshot()

    async def execute(self, progress_cb: Callable | None = None):
        steps = [
            ("SQLite → PostgreSQL 스키마 생성", self._migrate_schema),
            ("SQLite → PostgreSQL 데이터 이전", self._migrate_data),
            ("DATABASE_URL 교체", self._swap_db_url),
            ("Qdrant Local → Cloud 인덱스 재생성", self._migrate_qdrant),
            ("CURRENT_TIER 업데이트", self._update_tier_env),
        ]
        for i, (label, fn) in enumerate(steps):
            if progress_cb:
                await progress_cb(UpgradeProgress(i + 1, len(steps), label, int(i / len(steps) * 100)))
            fn()

    def _migrate_schema(self):
        print("📋 Alembic upgrade head 실행 (Supabase Postgres)...")
        pg_url = os.getenv("SUPABASE_URL", "")
        if not pg_url:
            print("⚠️  SUPABASE_URL 없음 — skip")
            return
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={**os.environ, "DATABASE_URL": pg_url},
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("✅ 스키마 마이그레이션 완료")
        else:
            print(f"❌ 마이그레이션 실패:\n{result.stderr[-500:]}")

    def _migrate_data(self):
        print("📦 SQLite → PostgreSQL 데이터 이전 (sqlite-to-postgres 방식)...")
        print("   ℹ️  데이터 이전은 scripts/migrate_sqlite_to_postgres.py 로 별도 실행하세요.")

    def _swap_db_url(self):
        pg_url = os.getenv("SUPABASE_URL", "")
        if pg_url:
            _update_env_key("DATABASE_URL", pg_url)
            print("✅ DATABASE_URL → Supabase PostgreSQL 전환됨")
        else:
            print("⚠️  SUPABASE_URL 없음 — DATABASE_URL 변경 skip")

    def _migrate_qdrant(self):
        qdrant_url = os.getenv("QDRANT_URL", "")
        if not qdrant_url or "localhost" in qdrant_url or "127.0.0.1" in qdrant_url:
            print("⚠️  QDRANT_URL 이 로컬입니다. 클라우드 URL 로 교체 후 재색인 필요.")
        else:
            print("✅ QDRANT_URL 이 이미 클라우드를 가리킵니다.")
            print("   ℹ️  재색인은 scripts/ingest_documents.py 실행으로 완료됩니다.")

    def _update_tier_env(self):
        _update_env_key("CURRENT_TIER", "tier_2")
        print("✅ CURRENT_TIER=tier_2 설정됨")

    async def verify(self) -> bool:
        pg_url = os.getenv("DATABASE_URL", "")
        return "supabase" in pg_url or "postgresql" in pg_url

    async def rollback(self, snapshot_id: str):
        full_restore(snapshot_id)
        _update_env_key("CURRENT_TIER", "tier_1_5")
        print("↩️  Tier 1.5 으로 롤백 완료. DATABASE_URL 을 SQLite 로 되돌리세요.")


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _update_env_key(key: str, value: str, env_path: str = ".env"):
    """`.env` 파일에서 key=value 줄을 업데이트하거나 추가."""
    lines: list[str] = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
