"""DB 스키마 복구: l1 마이그레이션이 부분 적용된 상태를 해결.

현상: alembic_version=k1 이나 ccp_rate_card 는 이미 존재, interaction 에 원가 컬럼 5종 누락.
원인: 이전 기동 시 l1 이 ccp_rate_card 생성까지 성공 후 interaction ALTER 에서 실패/중단.

복구: interaction 에 누락 컬럼 5종 + 인덱스 추가 → alembic_version 을 l1 로 stamp.
     (ccp_rate_card 는 이미 있으므로 재생성하지 않음. 데이터 손실 없음)
"""
import sqlalchemy

DB = "sqlite:///.gospel.db"
e = sqlalchemy.create_engine(DB, connect_args={"check_same_thread": False})


def run():
    with e.connect() as raw:
        raw.execute(sqlalchemy.text("BEGIN IMMEDIATE"))
        cols = [r[1] for r in raw.execute(sqlalchemy.text("PRAGMA table_info(interaction)")).fetchall()]
        adds = []
        if "llm_provider" not in cols:
            adds.append("llm_provider VARCHAR(40)")
        if "llm_model" not in cols:
            adds.append("llm_model VARCHAR(120)")
        if "prompt_tokens" not in cols:
            adds.append("prompt_tokens INTEGER")
        if "completion_tokens" not in cols:
            adds.append("completion_tokens INTEGER")
        if "cost_krw" not in cols:
            adds.append("cost_krw NUMERIC(18, 6)")
        if "rate_card_id" not in cols:
            adds.append("rate_card_id VARCHAR(40)")
        for a in adds:
            raw.execute(sqlalchemy.text(f"ALTER TABLE interaction ADD COLUMN {a}"))
        # 인덱스 (없으면 생성)
        idx = raw.execute(sqlalchemy.text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_interaction_llm_provider'"
        )).fetchall()
        if not idx:
            raw.execute(sqlalchemy.text(
                "CREATE INDEX ix_interaction_llm_provider ON interaction (llm_provider)"
            ))
        # alembic_version 을 l1 로 stamp
        raw.execute(sqlalchemy.text("UPDATE alembic_version SET version_num='l1_ccp_cost_attribution'"))
        raw.commit()
    print("OK: interaction 컬럼 보강 + alembic stamp l1 완료")


if __name__ == "__main__":
    run()
