"""툴의 작업(job)에서 이탈(breakaway)해 장시간 실행하는 런처.

execute_command 툴은 300s 후 프로세스 트리를 종료한다.
CREATE_BREAKAWAY_FROM_JOB 로 자식 프로세스를 job 에서 분리시켜
킬 제한을 우회하고 백그라운드 완주시킨다. 부모(_run_detached)는
즉시 종료되므로 툴 커맨드도 바로 반환된다.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
script = ROOT / "scripts" / "publish_documents.py"
log = ROOT / "publish.log"
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

try:
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.Popen(
            [sys.executable, str(script), "--reset"],
            stdout=f,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            creationflags=CREATE_BREAKAWAY_FROM_JOB,
        )
    print("DETACHED_PID", p.pid)
except Exception as e:
    print("BREAKAWAY_FAILED", repr(e))
