"""ユーザー設定（v2.3）。game/settings.json に保存する（リポジトリには含めない）。

ファイルが無い・壊れている・未知の値の場合は既定値を使う（起動を止めない）。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from systems.display import MODES, PIXEL_PERFECT

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


@dataclass
class Settings:
    display_mode: str = PIXEL_PERFECT   # 既定は従来の整数倍表示
    high_dpi: bool = False              # 既定は従来どおり DPI 非対応（Windows がビットマップ拡大）


def load(path: str | None) -> Settings:
    s = Settings()
    if not path or not os.path.exists(path):
        return s
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return s
    if not isinstance(data, dict):
        return s
    if data.get("display_mode") in MODES:
        s.display_mode = data["display_mode"]
    if isinstance(data.get("high_dpi"), bool):
        s.high_dpi = data["high_dpi"]
    return s


def save(settings: Settings, path: str | None) -> bool:
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
