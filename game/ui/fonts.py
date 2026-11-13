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

# UI で使う (サイズ, 太字) の組み合わせ。起動時に先読みし、初回描画でのフレーム落ちを防ぐ
# （v2.3: 日本語フォントの検索に約17ms、サイズごとの生成に約1ms かかり、
#   タイトル初回フレームやプレイ開始・テレポート直後の初回描画で 25〜38ms のフレームになっていた）
UI_FONT_SPECS: tuple[tuple[int, bool], ...] = (
    (72, True), (64, True), (24, False), (20, False), (20, True), (18, False), (18, True),
    (16, False), (16, True), (15, False), (14, False), (13, False),
)

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


def preload(specs=UI_FONT_SPECS) -> None:
    """フォントの検索と生成を先に済ませる（描画結果は変わらない）。

    pygame.quit() 後に作り直された Game でも古い Font を使わないよう、キャッシュを作り直す
    （フォントのパス検索結果は OS 依存で変わらないため保持する）。
    """
    _cache.clear()
    for size, bold in specs:
        get_font(size, bold)
