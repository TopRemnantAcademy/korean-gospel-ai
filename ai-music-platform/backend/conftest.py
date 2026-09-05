import sys
import os

# 确保 backend/ 在 sys.path 最前, 使 `import app` 解析到本项目的 backend/app 包
# (仓库内另有一个 korean-gospel-ai/backend/app, 不干预它的测试).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
