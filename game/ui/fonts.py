"""日本語表示に対応したフォントの取得。

OS にインストールされている日本語フォントを順に探す。見つからない場合は
pygame 既定フォントを使う（その場合は日本語が表示されないので README を参照）。
"""
from __future__ import annotations

import pygame

JP_FONT_CANDIDATES = [
    "yugothicmedium", "meiryo", "yugothicuiregular", "yugothic", "msgothic",  # Windows
    "hiraginosans", "hiraginokakugothicpro", "applegothic",  # macOS
    "notosanscjkjp", "notosansjp", "notosanscjk", "ipagothic", "takaogothic",  # Linux
]

_cache: dict[tuple[int, bool], pygame.font.Font] = {}
_resolved_path: str | None | bool = False


def _resolve() -> str | None:
    global _resolved_path
    if _resolved_path is False:
        path = None
        for name in JP_FONT_CANDIDATES:
            try:
                path = pygame.font.match_font(name)
            except Exception:
                path = None
            if path:
                break
        _resolved_path = path
    return _resolved_path  # type: ignore[return-value]


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _cache:
        if not pygame.font.get_init():
            pygame.font.init()
        path = _resolve()
        font = pygame.font.Font(path, size)
        font.set_bold(bold)
        _cache[key] = font
    return _cache[key]
