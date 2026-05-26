
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
# admin/pages/* 면 두 단계 위로, admin/* 면 한 단계 위로
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent  # admin -> project root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


