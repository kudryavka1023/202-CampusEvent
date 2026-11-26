"""ID 生成：集中一处，避免领域模块互相导入。"""
from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
