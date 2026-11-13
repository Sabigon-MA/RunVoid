"""表示スケーリング（v2.3）。内部解像度 960×540 のまま、ウィンドウへの拡大方法を切り替える。

モード:
    pixel_perfect … 整数倍のみ（従来どおり）。2倍に満たないウィンドウでは等倍で中央に置き、余白は黒帯。
    fit           … ウィンドウに収まる最大倍率（非整数可）。16:9 を保ち、余白は黒帯。補間は最近傍。

仕組み:
    pygame.SCALED が作る SDL レンダラーの「論理サイズ」機能をそのまま使い、
    SDL_RenderSetIntegerScale の ON/OFF だけを切り替える。
    マウスイベントの座標は SDL が描画と同じビューポートで内部座標へ変換するため、
    どちらのモードでもゲーム側の座標変換コード（Camera.to_world など）は変わらない。
    黒帯上のクリックは 0〜960 / 0〜540 の範囲外の座標になり、対象選択で除外される。

高DPI（Windows）:
    既定では DPI 非対応のまま（従来どおり。125%/150% では Windows がビットマップ拡大するためぼやける）。
    enable_high_dpi() を pygame.init() 前に呼ぶと SDL に Per-Monitor V2 を指定し、
    ウィンドウ座標が物理ピクセルになる（Windows の表示倍率そのものは変更しない）。
"""
from __future__ import annotations

import ctypes
import os
import sys

import pygame

PIXEL_PERFECT = "pixel_perfect"
FIT = "fit"
MODES = (PIXEL_PERFECT, FIT)
MODE_LABELS = {PIXEL_PERFECT: "Pixel Perfect", FIT: "Fit to Window"}


def compute_viewport(window_size, logical_size, mode: str):
    """SDL の論理サイズ計算と同じ配置を返す: (x, y, w, h, scale)。テスト・診断用。

    SDL 2.x の UpdateLogicalSize と同じく、縦横比を保つ最大倍率を求め、
    pixel_perfect では倍率を切り捨てて整数にする（1未満なら1）。
    """
    ww, wh = window_size
    lw, lh = logical_size
    scale = min(ww / lw, wh / lh)
    if mode == PIXEL_PERFECT:
        scale = max(1.0, float(int(scale)))
    w, h = lw * scale, lh * scale
    return (ww - w) / 2, (wh - h) / 2, w, h, scale


def window_to_internal(pos, window_size, logical_size, mode: str):
    """ウィンドウ座標 → 内部座標（SDL が行う変換の参照実装。黒帯は範囲外の値になる）。"""
    x, y, _, _, scale = compute_viewport(window_size, logical_size, mode)
    return (pos[0] - x) / scale, (pos[1] - y) / scale


#: ウィンドウの大きさ・位置・状態が変わったことを示すイベント。
#: Windows ではドラッグでのリサイズ・移動中はメインループが止まる（OS のモーダルループ）ため、
#: これらを受けたフレームは経過時間を 1 ステップ分に切り詰め、復帰直後の追いつき（最大 250 ms 分の
#: 物理更新の一括実行）を起こさない。
WINDOW_CHANGE_EVENTS = frozenset({
    pygame.VIDEORESIZE, pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED, pygame.WINDOWMOVED,
    pygame.WINDOWMAXIMIZED, pygame.WINDOWRESTORED, pygame.WINDOWMINIMIZED,
})


def enable_high_dpi() -> None:
    """pygame.init() より前に呼ぶ。Windows 以外では何もしない（SDL のヒントは無視される）。"""
    if sys.platform == "win32":
        os.environ["SDL_WINDOWS_DPI_AWARENESS"] = "permonitorv2"


class DisplayScaler:
    """SCALED ウィンドウの SDL レンダラーに対して整数倍スケーリングを切り替える。"""

    def __init__(self):
        self.mode = PIXEL_PERFECT
        self.supported = False      # SDL レンダラーを操作できたか（dummy ドライバ等では False）
        self._sdl = None
        self._renderer = None
        self._bind()

    def _bind(self) -> None:
        try:
            import warnings
            from pygame._sdl2.video import Window
            with warnings.catch_warnings():   # ウィンドウIDの取得だけに使う（描画には使わない）
                warnings.simplefilter("ignore", DeprecationWarning)
                win = Window.from_display_module()
            name = {"win32": "SDL2.dll", "darwin": "libSDL2-2.0.0.dylib"}.get(sys.platform, "libSDL2-2.0.so.0")
            path = os.path.join(os.path.dirname(pygame.__file__), name)
            sdl = ctypes.CDLL(path if os.path.exists(path) else name)
            sdl.SDL_GetWindowFromID.restype = ctypes.c_void_p
            sdl.SDL_GetWindowFromID.argtypes = [ctypes.c_uint32]
            sdl.SDL_GetRenderer.restype = ctypes.c_void_p
            sdl.SDL_GetRenderer.argtypes = [ctypes.c_void_p]
            sdl.SDL_RenderSetIntegerScale.restype = ctypes.c_int
            sdl.SDL_RenderSetIntegerScale.argtypes = [ctypes.c_void_p, ctypes.c_int]
            sdl.SDL_RenderGetIntegerScale.restype = ctypes.c_int
            sdl.SDL_RenderGetIntegerScale.argtypes = [ctypes.c_void_p]
            renderer = sdl.SDL_GetRenderer(sdl.SDL_GetWindowFromID(win.id))
        except Exception:   # pygame._sdl2 が無い・DLLが見つからない・ウィンドウが無い
            return
        if renderer:
            self._sdl, self._renderer, self.supported = sdl, renderer, True

    def apply(self, mode: str) -> str:
        """モードを適用し、実際に有効になったモードを返す。未対応環境では pixel_perfect のまま。"""
        if mode not in MODES:
            raise ValueError(f"unknown display mode: {mode!r}")
        if not self.supported:
            self.mode = PIXEL_PERFECT
            return self.mode
        if self._sdl.SDL_RenderSetIntegerScale(self._renderer, 1 if mode == PIXEL_PERFECT else 0) != 0:
            self.mode = PIXEL_PERFECT
            return self.mode
        self.mode = mode
        return self.mode

    def sync(self) -> bool:
        """選択中のモードを SDL レンダラーに再適用する（冪等）。設定がずれていて直した場合 True。

        pygame-ce は SCALED ウィンドウの最大化で整数倍を OFF、元に戻す（最小化からの復帰を含む）で
        ON に書き換える（pygame 内部のイベントウォッチ）。Fit 中に元に戻すと整数倍に戻ってしまうため、
        ウィンドウイベントを受けたフレームで描画前にこれを呼ぶ。
        Pixel Perfect の最大化時の挙動（pygame が非整数にする）は従来どおり変えない。
        """
        if not self.supported or self.mode != FIT:
            return False
        if self._sdl.SDL_RenderGetIntegerScale(self._renderer):
            self._sdl.SDL_RenderSetIntegerScale(self._renderer, 0)
            return True
        return False

    def integer_scale_enabled(self) -> bool | None:
        if not self.supported:
            return None
        return bool(self._sdl.SDL_RenderGetIntegerScale(self._renderer))

    def toggle(self) -> str:
        return self.apply(FIT if self.mode == PIXEL_PERFECT else PIXEL_PERFECT)
