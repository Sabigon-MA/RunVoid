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

v2.4 リサイズの即時反映（DisplayScaler.install_watch）:
    SDL_AddEventWatch のコールバックで、ウィンドウイベントを SDL がキューに積む瞬間に
    Fit 設定の再適用と最後のフレームの出し直しを行う（理由はクラスの説明を参照）。
    注意: コールバックは Python の GIL を取る。SDL のイベントを別スレッドから積む機能
    （pygame.time.set_timer、mixer の set_endevent 等）を使う場合は、pygame.event.get() が
    GIL を保持したまま SDL のイベントロックを待つと競合しうるので、導入時に確認すること（現在は未使用）。

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


class _Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


#: SDL_EventFilter: int (*)(void *userdata, SDL_Event *event)
_EVENT_FILTER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_SDL_WINDOWEVENT = 0x200
_WE_EXPOSED, _WE_RESIZED, _WE_SIZE_CHANGED, _WE_MAXIMIZED, _WE_RESTORED = 3, 5, 6, 8, 9
#: このプロセスで登録中のイベントウォッチ（Game を作り直しても 1 つだけにする）
_active_watch = None


class DisplayScaler:
    """SCALED ウィンドウの SDL レンダラーに対して整数倍スケーリングを切り替える。

    ウィンドウサイズ（OS のクライアント領域 = SDL の出力サイズ）と内部描画サイズ（960×540 の
    Surface = SDL の論理サイズ）は別物で、両者の対応（表示領域）は SDL がレンダラーに 1 組だけ持つ。
    描画もマウスイベントの座標変換もその同じ値を使う。

    v2.4: ウィンドウイベントを SDL がキューに積む瞬間に呼ばれるイベントウォッチ（install_watch）で
      - Fit の整数倍 OFF を再適用する。pygame-ce は「元に戻す」で整数倍を ON に書き換えるため、
        従来の sync()（event.get() の後）では、同じバッチで後に続くクリックが整数倍の配置で
        内部座標に変換されていた（実機で 4 回中 3 回再現）。
      - pumping() 中なら最後のフレームを新しいサイズで出し直す。Windows のドラッグリサイズ中は
        メインループが止まり、古いフレームが引き伸ばされたまま表示されていた。
    """

    def __init__(self):
        self.mode = PIXEL_PERFECT
        self.supported = False      # SDL レンダラーを操作できたか（dummy ドライバ等では False）
        self._sdl = None
        self._renderer = None
        self._window_id = None
        self._present = None        # ウィンドウ変更時に最後のフレームを出し直す関数
        self._pumping = False
        self.watch_installed = False
        self.live_presents = 0      # ウォッチから出し直した回数（診断用）
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
            sdl.SDL_RenderGetViewport.restype = None
            sdl.SDL_RenderGetViewport.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
            sdl.SDL_RenderGetScale.restype = None
            sdl.SDL_RenderGetScale.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                               ctypes.POINTER(ctypes.c_float)]
            sdl.SDL_GetRendererOutputSize.restype = ctypes.c_int
            sdl.SDL_GetRendererOutputSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                                      ctypes.POINTER(ctypes.c_int)]
            sdl.SDL_AddEventWatch.restype = None
            sdl.SDL_AddEventWatch.argtypes = [_EVENT_FILTER, ctypes.c_void_p]
            sdl.SDL_DelEventWatch.restype = None
            sdl.SDL_DelEventWatch.argtypes = [_EVENT_FILTER, ctypes.c_void_p]
            renderer = sdl.SDL_GetRenderer(sdl.SDL_GetWindowFromID(win.id))
        except Exception:   # pygame._sdl2 が無い・DLLが見つからない・ウィンドウが無い
            return
        if renderer:
            self._sdl, self._renderer, self.supported = sdl, renderer, True
            self._window_id = win.id

    # ------------------------------------------------------------------
    # ウィンドウイベントの即時処理（v2.4）
    # ------------------------------------------------------------------
    def install_watch(self, present=None) -> bool:
        """SDL のイベントウォッチを登録する。present は最後のフレームを出し直す関数（pygame.display.flip）。

        ウォッチは SDL_PushEvent の中で同期的に呼ばれる（Windows のドラッグ中のモーダルループ内も含む）。
        SDL のレンダラー自身のウォッチ（表示領域の更新・マウス座標の変換）と pygame-ce のウォッチより
        後に登録されるので、それらの後・次のイベント（クリック等）が積まれる前に実行される。
        """
        global _active_watch
        if not self.supported:
            return False
        if _active_watch is not None:
            _active_watch.remove_watch()
        self._present = present
        self._callback = _EVENT_FILTER(self._on_sdl_event)   # 参照を保持（GC されると落ちる）
        self._sdl.SDL_AddEventWatch(self._callback, None)
        self.watch_installed = True
        _active_watch = self
        return True

    def remove_watch(self) -> None:
        global _active_watch
        if self.watch_installed:
            try:
                self._sdl.SDL_DelEventWatch(self._callback, None)
            except Exception:
                pass
            self.watch_installed = False
        if _active_watch is self:
            _active_watch = None

    def pumping(self):
        """この with の間（= pygame.event.get() の中）に限り、ウォッチから最後のフレームを出し直す。

        それ以外（set_mode や Window.size の設定中など）では pygame の内部状態が途中の可能性があるため描かない。
        """
        scaler = self

        class _Pump:
            def __enter__(self_):
                scaler._pumping = True

            def __exit__(self_, *exc):
                scaler._pumping = False
                return False
        return _Pump()

    def _on_sdl_event(self, _userdata, event_ptr) -> int:
        try:
            raw = ctypes.string_at(event_ptr, 13)
            if int.from_bytes(raw[0:4], "little") != _SDL_WINDOWEVENT:
                return 0
            if int.from_bytes(raw[8:12], "little") != self._window_id:
                return 0
            kind = raw[12]
            if kind in (_WE_RESIZED, _WE_SIZE_CHANGED, _WE_MAXIMIZED, _WE_RESTORED):
                # 別のウィンドウ／作り直したレンダラーに対しては何もしない
                if self._sdl.SDL_GetRenderer(self._sdl.SDL_GetWindowFromID(self._window_id)) != self._renderer:
                    return 0
                self.sync()
            if (kind in (_WE_SIZE_CHANGED, _WE_EXPOSED, _WE_RESTORED, _WE_MAXIMIZED)
                    and self._pumping and self._present is not None):
                self._present()
                self.live_presents += 1
        except Exception:   # ウォッチ内の例外は SDL に伝えられない。表示の出し直しは次のフレームで行われる
            pass
        return 0

    # ------------------------------------------------------------------
    # 診断: SDL が実際に使っている値
    # ------------------------------------------------------------------
    def output_size(self):
        """ウィンドウの描画先サイズ（SDL レンダラーの出力サイズ。高DPI 時は物理px）。"""
        if not self.supported:
            return None
        w, h = ctypes.c_int(), ctypes.c_int()
        self._sdl.SDL_GetRendererOutputSize(self._renderer, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def actual_viewport(self):
        """SDL が描画とマウス変換に使っている表示領域を、ウィンドウ座標の (x, y, w, h, scale) で返す。"""
        if not self.supported:
            return None
        r = _Rect()
        sx, sy = ctypes.c_float(), ctypes.c_float()
        self._sdl.SDL_RenderGetViewport(self._renderer, ctypes.byref(r))
        self._sdl.SDL_RenderGetScale(self._renderer, ctypes.byref(sx), ctypes.byref(sy))
        s = sx.value
        return r.x * s, r.y * s, r.w * s, r.h * s, s

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
