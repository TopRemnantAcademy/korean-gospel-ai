import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db import get_session
from backend.app.models.orm import DocumentVersion, DocVersionState
from collections import Counter

with get_session() as s:
    vs = s.query(DocumentVersion).all()
    print("TOTAL", len(vs))
    print("BY_STATE", dict(Counter(v.state for v in vs)))
    pub = s.query(DocumentVersion).filter(DocumentVersion.state == DocVersionState.published.value).all()
    print("PUBLISHED", len(pub))
    for v in pub:
        print("  PUB", v.title)
