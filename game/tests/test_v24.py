"""v2.4: 表示安定化（Fit のリサイズ）・フレーム待機・穴の視認性の回帰テスト。

表示まわりは SDL dummy ドライバのソフトウェアレンダラーで、実際の SDL の処理を通して確認する。
ウィンドウイベント・クリックは SDL_PushEvent で SDL のキューへ積むので、SDL のレンダラー自身の
イベントウォッチ（表示領域の更新・マウス座標の内部座標への変換）と pygame-ce のウォッチがそのまま動く。
OS のリサイズ操作・DPI・画面に出た画像の一致は tests/AIMING_CHECKLIST.md の実機記録を参照。
"""
from __future__ import annotations

import ctypes
import struct
import unittest

from test_gameplay import DT, STAGE_1  # noqa: F401  (SDL dummy 設定を含む)

import pygame

import config
from systems import display

L = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
_WE_RESIZED, _WE_SIZE_CHANGED, _WE_MAXIMIZED, _WE_RESTORED = 5, 6, 8, 9


class SDLWindow:
    """テスト用: Game のウィンドウに SDL の関数で直接サイズ変更・イベント投入を行う。"""

    def __init__(self, scaler: display.DisplayScaler):
        self.s = scaler
        sdl = scaler._sdl
        sdl.SDL_SetWindowSize.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        sdl.SDL_SetWindowSize.restype = None
        sdl.SDL_PushEvent.argtypes = [ctypes.c_void_p]
        sdl.SDL_PushEvent.restype = ctypes.c_int
        self.sdl = sdl
        self.win = sdl.SDL_GetWindowFromID(scaler._window_id)

    def resize(self, w, h):
        self.sdl.SDL_SetWindowSize(self.win, w, h)   # SDL が SIZE_CHANGED を積む（dummy でも同じ）

    def _push(self, raw: bytes):
        buf = ctypes.create_string_buffer(raw.ljust(56, b"\0"), 56)
        assert self.sdl.SDL_PushEvent(buf) == 1

    def window_event(self, kind, d1=0, d2=0):
        self._push(struct.pack("<IIIBxxxii", 0x200, 0, self.s._window_id, kind, d1, d2))

    def click(self, x, y):
        """ウィンドウ座標でのクリック（SDL が積む前に内部座標へ変換する）。"""
        self._push(struct.pack("<IIIIBBBxii", 0x401, 0, self.s._window_id, 0, 1, 1, 1, int(x), int(y)))


def make_game(test: unittest.TestCase, mode):
    """Game を作り、テスト終了時にウィンドウを 960×540 に戻してウォッチを外す。

    pygame-ce 2.5.8 は、SCALED ウィンドウを 2 回以上リサイズした後に set_mode を呼び直すと
    （= 次の Game を作ると）dummy ドライバで落ちることがある（ウォッチの有無に関係なく再現）。
    ゲーム本体は set_mode を 1 回しか呼ばないため、テスト側で元のサイズに戻してから次へ進む。
    """
    import main
    game = main.Game(display_mode=mode)
    if not game.display.supported:
        raise unittest.SkipTest("SDL renderer unavailable in this environment")
    win = SDLWindow(game.display)

    def restore():
        game.display.remove_watch()
        win.resize(*L)
        pygame.event.get()
    test.addCleanup(restore)
    return game, win


def pump(game):
    with game.display.pumping():
        return pygame.event.get()


def downs(events):
    return [e.pos for e in events if e.type == pygame.MOUSEBUTTONDOWN]


class FitResizeTests(unittest.TestCase):
    """Task 1: ウィンドウサイズ（SDL の出力サイズ）と内部描画サイズ（960×540）の対応。"""

    SIZES = [(960, 540), (1200, 675), (1000, 700), (1500, 700), (1280, 720), (1100, 900), (1536, 864),
             (1920, 991), (2560, 1440)]

    def test_actual_sdl_viewport_follows_every_resize_immediately(self):
        # リサイズを SDL が受けた直後（event.get() の前）から、SDL が描画に使う表示領域が新しいサイズの配置になる
        for mode in display.MODES:
            game, win = make_game(self, mode)
            for size in self.SIZES:
                win.resize(*size)
                self.assertEqual(game.display.output_size(), size)
                x, y, w, h, s = game.display.actual_viewport()
                ex, ey, ew, eh, es = display.compute_viewport(size, L, mode)
                for a, b in ((x, ex), (y, ey), (w, ew), (h, eh)):
                    self.assertLessEqual(abs(a - b), es + 0.5, (mode, size))   # SDL の整数ビューポート分の誤差
                self.assertAlmostEqual(s, es, places=4)
                pump(game)
            win.resize(*L)   # 次の Game の前に元のサイズへ（make_game の説明を参照）
            pygame.event.get()

    def test_click_in_same_batch_as_restore_uses_fit_layout(self):
        # 根本原因: pygame-ce は「元に戻す」で整数倍を ON に書き換える。従来は event.get() の後で
        # 戻していたため、同じバッチのクリックは整数倍の配置で内部座標に変換されていた
        game, win = make_game(self, display.FIT)
        win.resize(1200, 600)
        pump(game)
        win.window_event(_WE_RESTORED)
        win.click(300, 100)
        self.assertIs(game.display.integer_scale_enabled(), False)
        fit = display.window_to_internal((300, 100), (1200, 600), L, display.FIT)   # (210, 90)
        (pos,) = downs(pump(game))
        self.assertLessEqual(max(abs(pos[0] - fit[0]), abs(pos[1] - fit[1])), 1.5)
        # ウォッチなし（従来の sync() だけ）では整数倍の配置で変換される = 不具合の再現
        game.display.remove_watch()
        win.window_event(_WE_RESTORED)
        win.click(300, 100)
        old = display.window_to_internal((300, 100), (1200, 600), L, display.PIXEL_PERFECT)   # (180, 70)
        (pos,) = downs(pump(game))
        self.assertEqual(pos, (int(old[0]), int(old[1])))
        game.display.sync()

    def test_clicks_match_drawn_layout_in_both_modes_and_letterbox_is_ignored(self):
        from systems.targeting import find_target
        from test_v20 import teleport_world
        for mode in display.MODES:
            game, win = make_game(self, mode)
            for size in ((1200, 600), (1000, 700), (1536, 864), (1280, 720), (1100, 900)):
                win.resize(*size)
                for event in (None, _WE_MAXIMIZED, _WE_RESTORED):
                    if event is not None and mode == display.FIT:
                        win.window_event(event)   # Pixel Perfect の最大化の扱いは pygame の従来挙動のまま
                    w, _, e = teleport_world()
                    x, y, vw, vh, s = display.compute_viewport(size, L, mode)
                    sx, sy = w.camera.to_screen(*e.hurtbox.center)
                    win.click(x + sx * s, y + sy * s)          # 敵が描かれているウィンドウ上の点
                    if x >= 2:
                        win.click(x / 2, size[1] / 2)          # 左の黒帯
                    if y >= 2:
                        win.click(size[0] / 2, y / 2)          # 上の黒帯
                    got = downs(pump(game))
                    self.assertIs(find_target(w.enemies, w.camera, w.camera.to_world(*got[0])), e,
                                  (mode, size, event))
                    for p in got[1:]:
                        self.assertFalse(0 <= p[0] < L[0] and 0 <= p[1] < L[1], (mode, size, p))
                        self.assertIsNone(find_target(w.enemies, w.camera, w.camera.to_world(*p)))
            win.resize(*L)   # 次の Game の前に元のサイズへ（make_game の説明を参照）
            pygame.event.get()

    def test_pixel_perfect_keeps_integer_scaling_on_resize_and_restore(self):
        game, win = make_game(self, display.PIXEL_PERFECT)
        for size in ((1200, 675), (1920, 1080), (1500, 700)):
            win.resize(*size)
            win.window_event(_WE_RESTORED)
            pump(game)
            self.assertIs(game.display.integer_scale_enabled(), True)
            *_, s = game.display.actual_viewport()
            self.assertEqual(s, display.compute_viewport(size, L, display.PIXEL_PERFECT)[4])

    def test_window_change_re_presents_last_frame_only_while_pumping(self):
        game, win = make_game(self, display.FIT)
        presented = []
        game.display._present = lambda: presented.append(game.display.output_size())
        win.resize(1300, 700)                  # event.get() の外（set_mode 等の最中を想定）では描かない
        self.assertEqual(presented, [])
        pump(game)                             # 積まれていた分は描き直し済みの扱い（再提示しない）
        game.display._pumping = True
        try:
            win.resize(1400, 800)              # Windows のドラッグ中は event.get() の中でこれが起きる
        finally:
            game.display._pumping = False
        self.assertEqual(presented, [(1400, 800)])
        pump(game)

    def test_watch_and_redraw_never_change_the_window_size(self):
        game, win = make_game(self, display.FIT)
        game.start_play()
        for size in ((1200, 675), (1566, 864), (1536, 864), (1000, 700)):
            win.resize(*size)
            for kind in (_WE_SIZE_CHANGED, _WE_RESTORED, _WE_MAXIMIZED):
                win.window_event(kind, *size)
            game.step_frame(DT)
            game.step_frame(DT)
            self.assertEqual(pygame.display.get_window_size(), size)
            self.assertEqual(game.display.output_size(), size)
            self.assertEqual(game.screen.get_size(), L)      # 内部解像度は固定
            self.assertEqual(game.window.get_size(), L)

    def test_only_one_watch_per_process_and_removal(self):
        import main
        a = main.Game(display_mode=display.FIT)
        if not a.display.supported:
            self.skipTest("SDL renderer unavailable")
        b = main.Game(display_mode=display.FIT)
        self.assertFalse(a.display.watch_installed)        # 作り直すと古いウォッチは外れる
        self.assertTrue(b.display.watch_installed)
        b.display.remove_watch()
        self.assertFalse(b.display.watch_installed)
        self.assertIsNone(display._active_watch)

    def test_unsupported_renderer_has_no_watch(self):
        class NoRenderer(display.DisplayScaler):
            def _bind(self):
                pass
        s = NoRenderer()
        self.assertFalse(s.install_watch(present=lambda: None))
        self.assertIsNone(s.actual_viewport())
        self.assertIsNone(s.output_size())
        with s.pumping():
            pass


if __name__ == "__main__":
    unittest.main()
