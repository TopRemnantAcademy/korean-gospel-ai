"""
초대 코드 시스템 (Invite Code System)
- 베타 초대 코드 생성, 검증, 추적
- SQLite 저장 (자체 DB)
- 일일 접속 IP 로깅
"""
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import os

DB_PATH = Path(__file__).parent.parent / "data" / "invite_codes.db"
LOG_PATH = Path(__file__).parent.parent / "user" / "logs"


def init_db():
    """초대 코드 DB 초기화"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 초대 코드 테이블
    c.execute("""
    CREATE TABLE IF NOT EXISTS invite_codes (
        code TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        created_by TEXT,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0,
        active BOOLEAN DEFAULT 1
    )
    """)
    
    # 코드 사용 기록
    c.execute("""
    CREATE TABLE IF NOT EXISTS code_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        user_id TEXT,
        used_at TEXT NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        FOREIGN KEY(code) REFERENCES invite_codes(code)
    )
    """)
    
    # 접속 IP 로그 (일일)
    c.execute("""
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        user_id TEXT,
        code_used TEXT,
        access_count INTEGER DEFAULT 1,
        UNIQUE(date, ip_address)
    )
    """)
    
    conn.commit()
    conn.close()


def generate_invite_code(max_uses: int = 1, expires_hours: int = 24 * 7, created_by: str = "admin") -> str:
    """
    초대 코드 생성
    
    Args:
        max_uses: 최대 사용 횟수 (None = 무제한)
        expires_hours: 만료 시간 (시간)
        created_by: 생성자
    
    Returns:
        BETA-GOSPEL-XXXXXX 형태의 코드
    """
    init_db()
    
    code = f"BETA-GOSPEL-{uuid.uuid4().hex[:6].upper()}"
    created_at = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(hours=expires_hours)).isoformat() if expires_hours else None
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
    INSERT INTO invite_codes (code, created_at, expires_at, created_by, max_uses)
    VALUES (?, ?, ?, ?, ?)
    """, (code, created_at, expires_at, created_by, max_uses))
    
    conn.commit()
    conn.close()
    
    return code


def validate_invite_code(code: str, ip_address: str = None, user_agent: str = None) -> dict:
    """
    초대 코드 검증
    
    Returns:
        {
            'valid': bool,
            'reason': str,
            'code_info': {code, created_at, expires_at, used_count, max_uses}
        }
    """
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return {'valid': False, 'reason': '존재하지 않는 코드입니다.'}
    
    code, created_at, expires_at, created_by, max_uses, used_count, active = row
    
    # 활성화 여부
    if not active:
        conn.close()
        return {'valid': False, 'reason': '비활성화된 코드입니다.'}
    
    # 만료 여부
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
        conn.close()
        return {'valid': False, 'reason': '만료된 코드입니다.'}
    
    # 사용 횟수 초과
    if max_uses and used_count >= max_uses:
        conn.close()
        return {'valid': False, 'reason': f'사용 횟수 초과입니다. (최대 {max_uses}회)'}
    
    # 유효함
    c.execute("""
    UPDATE invite_codes SET used_count = used_count + 1 WHERE code = ?
    """, (code,))
    
    if ip_address and user_agent:
        c.execute("""
        INSERT INTO code_usage (code, used_at, ip_address, user_agent)
        VALUES (?, ?, ?, ?)
        """, (code, datetime.now().isoformat(), ip_address, user_agent))
    
    conn.commit()
    conn.close()
    
    return {
        'valid': True,
        'reason': 'OK',
        'code_info': {
            'code': code,
            'created_at': created_at,
            'expires_at': expires_at,
            'used_count': used_count + 1,
            'max_uses': max_uses,
        }
    }


def log_access(ip_address: str, user_id: str = None, code_used: str = None):
    """접속 IP 로깅 (일일)"""
    init_db()
    
    date = datetime.now().date().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
    INSERT INTO access_logs (date, ip_address, user_id, code_used, access_count)
    VALUES (?, ?, ?, ?, 1)
    ON CONFLICT(date, ip_address) DO UPDATE SET
        access_count = access_count + 1,
        user_id = COALESCE(excluded.user_id, user_id),
        code_used = COALESCE(excluded.code_used, code_used)
    """, (date, ip_address, user_id, code_used))
    
    conn.commit()
    conn.close()


def get_daily_access_report() -> list:
    """일일 접속 보고서"""
    init_db()
    
    date = datetime.now().date().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
    SELECT ip_address, access_count, user_id, code_used
    FROM access_logs
    WHERE date = ?
    ORDER BY access_count DESC
    """, (date,))
    
    rows = c.fetchall()
    conn.close()
    
    return [
        {
            'ip': row[0],
            'access_count': row[1],
            'user_id': row[2],
            'code_used': row[3],
        }
        for row in rows
    ]


def get_invite_code_stats() -> dict:
    """초대 코드 통계"""
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
    SELECT COUNT(*), SUM(used_count) FROM invite_codes WHERE active = 1
    """)
    total_codes, total_uses = c.fetchone()
    total_codes = total_codes or 0
    total_uses = total_uses or 0
    
    c.execute("""
    SELECT COUNT(DISTINCT ip_address) FROM access_logs WHERE date = ?
    """, (datetime.now().date().isoformat(),))
    today_unique_ips = c.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_codes': total_codes,
        'total_uses': total_uses,
        'today_unique_ips': today_unique_ips,
    }


def export_access_logs(output_path: str = None):
    """접속 로그 내보내기 (CSV)"""
    if not output_path:
        output_path = LOG_PATH / f"access_logs_{datetime.now().date()}.csv"
    
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM access_logs ORDER BY date DESC")
    rows = c.fetchall()
    conn.close()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("date,ip_address,user_id,code_used,access_count\n")
        for row in rows:
            f.write(f"{row[1]},{row[2]},{row[3]},{row[4]},{row[5]}\n")
    
    return output_path


if __name__ == "__main__":
    # 테스트
    init_db()
    
    # 코드 생성
    code = generate_invite_code(max_uses=5)
    print(f"✅ 초대 코드 생성: {code}")
    
    # 검증
    result = validate_invite_code(code, ip_address="192.168.1.1", user_agent="test")
    print(f"✅ 검증: {result}")
    
    # 로깅
    log_access("192.168.1.1", user_id="user123", code_used=code)
    print(f"✅ 접속 로깅 완료")
    
    # 통계
    stats = get_invite_code_stats()
    print(f"📊 통계: {stats}")
    
    # 일일 보고서
    report = get_daily_access_report()
    print(f"📈 일일 보고서: {report}")
