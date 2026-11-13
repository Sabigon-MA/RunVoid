"""v2.3: 実機QA反映（フォント先読み・表示モード・視認性・テレポート時カメラ）の回帰テスト。

物理トレース:
    tests/fixtures/physics_trace_v22.json は v2.2（コミット 1ffc37e）のコードで記録した、ステージ1の
    自動プレイ3通りの毎ステップの状態（主人公の位置・速度・接地・HP、追跡壁、カメラX、交換回数、敵の位置）。
    v2.3 の変更はすべて見た目・表示だけなので完全一致すること（カメラの動きも変えていない）。
    再生成（ゲームルールを意図的に変えたときのみ）:
        set RUNVOID_REGEN_TRACE=1 && python -m unittest tests.test_v23
"""
from __future__ import annotations

import json
import os
import re
import unittest

from test_gameplay import DT, STAGE_1, InputState  # noqa: F401  (SDL dummy 設定を含む)

import config
import settings as settings_mod
from systems import display
from systems.world import PLAYING, World
from ui import fonts

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE_PATH = os.path.join(HERE, "fixtures", "physics_trace_v22.json")
GROUND = 422.0
ROUTE = [(980, GROUND, False), (1200, GROUND, False), (1405, 300, True),
         (2270, GROUND, False), (2400, GROUND, False), (2605, 310, True)]


def run_trace(use_teleport: bool, target_id: str | None = None, with_graphics: bool = False):
    """Stage1BalanceTests と同じ自動操作で 1 プレイし、毎ステップの状態を記録する。"""
    w = World(STAGE_1, with_graphics=with_graphics)
    inp = InputState()
    inp.simulate_press("right")
    used, double, hold = set(), False, 0
    rows = []
    for _ in range(60 * 15):
        p = w.player
        if hold > 0:
            hold -= 1
            if hold == 0:
                inp.simulate_release("jump")
        if double and p.vy >= -30 and not p.on_ground:
            inp.simulate_release("jump")
            inp.simulate_press("jump")
            hold, double = 40, False
        jumped = False
        if p.on_ground:
            for i, (x, surf, dbl) in enumerate(ROUTE):
                if i not in used and abs(p.rect.bottom - surf) < 1 and p.rect.right >= x:
                    used.add(i)
                    inp.simulate_release("jump")
                    inp.simulate_press("jump")
                    hold, double, jumped = 40, dbl, True
                    break
        near = any(i not in used and abs(p.rect.bottom - s) < 1 and x - 140 <= p.rect.right < x
                   for i, (x, s, _) in enumerate(ROUTE))
        if p.on_ground and p.dash_cooldown <= 0 and not jumped and not near:
            inp.simulate_press("dash")
        else:
            inp.simulate_release("dash")
        if use_teleport and w.teleport.ready:
            ahead = [e for e in w.enemies if w.camera.view_rect.contains(e.hurtbox)
                     and e.x - p.rect.centerx > 250
                     and (target_id is None or e.enemy_id == target_id)]
            if ahead:
                e = max(ahead, key=lambda e: e.x)
                inp.mouse_pos = w.camera.to_screen(*e.hurtbox.center)
                inp.simulate_press("teleport")
        if w.update(DT, inp):
            inp.clear_edges()
        inp.simulate_release("teleport")
        rows.append([round(v, 4) for v in (p.rect.x, p.rect.y, p.vx, p.vy, w.wall.front_x, w.camera.x)]
                    + [int(p.on_ground), p.hp, w.teleport.count]
                    + [[e.enemy_id, round(e.x, 4), round(e.foot_y, 4)] for e in w.enemies])
        if w.state != PLAYING:
            break
    return dict(state=w.state, elapsed=round(w.elapsed, 4), rows=rows)


SCENARIOS = {"no_teleport": (False, None), "teleport": (True, None), "e03_only": (True, "E03")}


def build_traces(with_graphics: bool = False):
    return {k: run_trace(tp, tid, with_graphics) for k, (tp, tid) in SCENARIOS.items()}


if os.environ.get("RUNVOID_REGEN_TRACE") == "1":   # pragma: no cover - 手動再生成用
    with open(TRACE_PATH, "w", encoding="utf-8") as f:
        json.dump(build_traces(), f, separators=(",", ":"))


class PhysicsTraceTests(unittest.TestCase):
    """v2.3 の表示変更でゲームプレイが変わっていないこと（v2.2 の記録と完全一致）。"""

    @classmethod
    def setUpClass(cls):
        with open(TRACE_PATH, encoding="utf-8") as f:
            cls.expected = json.load(f)

    def _check(self, actual):
        for name, exp in self.expected.items():
            act = actual[name]
            self.assertEqual(act["state"], exp["state"], name)
            self.assertEqual(act["elapsed"], exp["elapsed"], name)
            self.assertEqual(len(act["rows"]), len(exp["rows"]), name)
            for i, (a, e) in enumerate(zip(act["rows"], exp["rows"])):
                self.assertEqual(a, e, f"{name} step {i}")

    def test_trace_matches_v22_without_graphics(self):
        self._check(build_traces(with_graphics=False))

    def test_trace_matches_v22_with_graphics(self):
        # 描画用オブジェクト（背景・地形描画・テレポート演出）があっても挙動は同じ
        self._check(build_traces(with_graphics=True))


class FontPreloadTests(unittest.TestCase):
    """作業B: 初回描画でのフォント検索・生成によるフレーム落ち対策。"""

    def test_every_ui_text_size_is_preloaded(self):
        ui_dir = os.path.join(os.path.dirname(HERE), "ui")
        used = set()
        for name in os.listdir(ui_dir):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(ui_dir, name), encoding="utf-8") as f:
                src = f.read()
            for m in re.finditer(r"draw_text\([^\n]*?,\s*(\d+)\s*,", src):
                used.add(int(m.group(1)))
        specs = {s for s, _ in fonts.UI_FONT_SPECS}
        self.assertTrue(used, "draw_text の呼び出しが見つからない")
        self.assertLessEqual(used, specs, f"先読みしていないサイズ: {sorted(used - specs)}")
        self.assertIn(24, specs)   # Button の既定サイズ

    def test_preload_fills_cache_without_changing_fonts(self):
        fonts.preload()
        for spec in fonts.UI_FONT_SPECS:
            self.assertIn(spec, fonts._cache)
            self.assertIs(fonts.get_font(*spec), fonts._cache[spec])
            self.assertEqual(fonts.get_font(*spec).get_bold(), spec[1])


class VisibilityTests(unittest.TestCase):
    """作業D: 敵・穴の視認性（描画のみ。判定・位置・背景素材は変えない）。"""

    def _world(self):
        import pygame
        pygame.display.set_mode((960, 540))
        return World(STAGE_1)

    def test_pits_are_the_gaps_in_the_floor_only(self):
        from stages.renderer import find_pits
        rects = [p.to_rect() for p in STAGE_1.platforms]
        self.assertEqual(find_pits(rects, STAGE_1.world_width, 540), [(1040, 1150, 422), (2300, 2420, 422)])
        # 城壁 B01/B02 は地面と接しているので穴ではない
        self.assertNotIn(1560, [x for p in find_pits(rects, STAGE_1.world_width, 540) for x in p[:2]])

    def test_pit_interior_turns_red_toward_the_bottom_and_edges_are_lighter(self):
        import pygame
        w = self._world()
        w.camera.x = 400.0
        s = pygame.Surface((960, 540))
        w.terrain_renderer.draw(s, w.camera)
        cx = 1095 - 400
        top, bottom = s.get_at((cx, 430)), s.get_at((cx, 536))
        self.assertGreater(bottom.r, top.r + 40)            # 底が赤く光る
        self.assertGreater(bottom.r, bottom.g * 3)
        ground = s.get_at((1040 - 400 - 40, 470))           # 地面の内側
        edge = s.get_at((1040 - 400 - 2, 430))              # 穴に面した縁
        self.assertGreater(sum(edge[:3]), sum(ground[:3]) + 60)
        # 地形の当たり判定（collision.Terrain）は描画と無関係で、穴は固体ではない
        self.assertFalse(w.terrain.point_in_solid(1095, 500))

    def test_enemy_rim_and_targets_are_drawn_without_changing_hitboxes(self):
        import pygame
        from systems.targeting import pick_rect
        w = self._world()
        e = w.enemies[0]
        before = (e.body_rect.copy(), e.hurtbox.copy(), pick_rect(e).copy())
        s = pygame.Surface((960, 540))
        w.draw(s)
        rim = tuple(config.COLORS["enemy_rim"])
        sx, sy = w.camera.to_screen(e.x, e.foot_y)
        found = any(tuple(s.get_at((x, y))[:3]) == rim
                    for x in range(int(sx) - 26, int(sx) + 26) for y in range(int(sy) - 24, int(sy)))
        self.assertTrue(found, "敵の縁取りが描かれていない")
        self.assertEqual(before, (e.body_rect, e.hurtbox, pick_rect(e)))

    def test_target_marker_follows_targetability_and_cooldown(self):
        import pygame
        from systems.targeting import is_targetable
        w = self._world()
        tele, dim = tuple(config.COLORS["teleport"]), tuple(config.COLORS["teleport_dim"])

        def marker_color(enemy):
            s = pygame.Surface((960, 540))
            s.fill((0, 0, 0))
            w._draw_target_markers(s)
            x = round(enemy.hurtbox.centerx - w.camera.x)
            y = round(enemy.hurtbox.top - w.camera.y) - 12
            return tuple(s.get_at((x, y))[:3]) if 0 <= x < 960 else None

        visible = [e for e in w.enemies if is_targetable(e, w.camera)]
        hidden = [e for e in w.enemies if not is_targetable(e, w.camera)]
        self.assertTrue(visible and hidden)
        for e in visible:
            self.assertEqual(marker_color(e), tele)
        w.teleport.cooldown_remaining = 1.0
        for e in visible:
            self.assertEqual(marker_color(e), dim)
        # 画面外の敵には描かない（描画先の範囲外）
        for e in hidden:
            self.assertIsNone(marker_color(e))

    def test_visibility_can_be_disabled(self):
        import pygame
        saved = dict(config.VISIBILITY)
        try:
            config.VISIBILITY.update(enemy_halo_alpha=0, enemy_rim_width=0, target_marker=False)
            w = self._world()
            s = pygame.Surface((960, 540))
            w.draw(s)
            rim = tuple(config.COLORS["enemy_rim"])
            self.assertFalse(any(tuple(s.get_at((x, y))[:3]) == rim
                                 for x in range(0, 960, 2) for y in range(380, 440)))
        finally:
            config.VISIBILITY.clear()
            config.VISIBILITY.update(saved)


class TeleportCueTests(unittest.TestCase):
    """作業E: テレポート直後の画面演出（流線・ロケーター）。カメラの動きは変えない（トレースで保証）。"""

    def _teleport(self, enemy_x):
        """平地で主人公（x=100）と enemy_x の敵を交換する。カメラは x=0（左端に寄った状態）。"""
        import pygame
        from test_v20 import custom_world
        pygame.display.set_mode((960, 540))
        w = custom_world([(0, 422, 3000, 118)], enemies=[(enemy_x, 422)])
        e = w.enemies[0]
        cam_before = w.camera.x
        self.assertTrue(w.teleport.try_teleport(w, e).ok)
        return w, cam_before

    def test_large_camera_move_gets_streaks_and_locator(self):
        w, cam_before = self._teleport(900)          # 画面右寄りの敵 → カメラが大きく右へ動く
        self.assertTrue(w.effects.streaks)
        self.assertEqual(len(w.effects.locators), 1)
        self.assertIs(w.effects.locators[0][0], w.player)
        # 背景は右へ動くカメラと逆（左）へ流れる
        self.assertTrue(all(s[3] < 0 for s in w.effects.streaks))

    def test_small_camera_move_has_locator_only(self):
        w, _ = self._teleport(170)                   # カメラは左端のまま（移動量 0）
        self.assertEqual(w.effects.streaks, [])
        self.assertEqual(len(w.effects.locators), 1)

    def test_cues_expire_and_draw(self):
        import pygame
        w, _ = self._teleport(900)
        s = pygame.Surface((960, 540))
        for _ in range(int(0.4 / DT) + 2):
            w.draw(s)
            w.effects.update(DT)
        self.assertEqual((w.effects.streaks, w.effects.locators), ([], []))

    def test_cues_can_be_disabled(self):
        saved = dict(config.TELEPORT_FX)
        try:
            config.TELEPORT_FX.update(streaks=False, locator=False)
            w, _ = self._teleport(900)
            self.assertEqual((w.effects.streaks, w.effects.locators), ([], []))
        finally:
            config.TELEPORT_FX.clear()
            config.TELEPORT_FX.update(saved)


class DisplayLayoutTests(unittest.TestCase):
    """作業C: 表示モードの配置計算（SDL の論理サイズ計算の参照実装）。

    実際の変換は SDL が行う。ここでは実機（Windows 125%）で観測した値と同じになることと、
    黒帯・カメラ移動を含めた対象選択がどちらのモードでも一致することを確認する。
    実画面での一致は AIMING_CHECKLIST.md の実機記録を参照（このテストは実機合格の代わりにならない）。
    """
    L = (960, 540)

    def test_pixel_perfect_matches_observed_sdl_viewports(self):
        # 実機で Renderer.get_viewport() から得た値（論理ウィンドウサイズ → 余白）
        for win, (ox, oy) in {(1200, 675): (120, 67.5), (1280, 720): (160, 90),
                              (1000, 700): (20, 80), (960, 540): (0, 0), (1920, 1080): (0, 0)}.items():
            x, y, w, h, s = display.compute_viewport(win, self.L, display.PIXEL_PERFECT)
            self.assertEqual((x, y), (ox, oy), win)
            self.assertEqual(s, 2.0 if win == (1920, 1080) else 1.0)

    def test_fit_uses_largest_non_integer_scale_keeping_16_9(self):
        for win, scale in {(1200, 675): 1.25, (1280, 720): 4 / 3, (1536, 864): 1.6, (1000, 700): 1000 / 960}.items():
            x, y, w, h, s = display.compute_viewport(win, self.L, display.FIT)
            self.assertAlmostEqual(s, scale)
            self.assertAlmostEqual(w / h, 16 / 9)
            self.assertTrue(w <= win[0] + 1e-9 and h <= win[1] + 1e-9)
            self.assertTrue(abs(w - win[0]) < 1e-6 or abs(h - win[1]) < 1e-6, "片方の辺はウィンドウに接する")
        # 実機の Renderer.get_viewport(): 1000×700 で上下に (700-562.5)/2 の黒帯
        x, y, *_ = display.compute_viewport((1000, 700), self.L, display.FIT)
        self.assertAlmostEqual(y, 68.75)

    def test_letterbox_maps_outside_internal_screen_in_both_modes(self):
        for mode in display.MODES:
            for win in ((1280, 720), (1000, 700), (1200, 600), (960, 800)):
                x, y, w, h, _ = display.compute_viewport(win, self.L, mode)
                for p in ((x / 2, win[1] / 2), (win[0] / 2, y / 2),
                          (win[0] - x / 2, win[1] / 2), (win[0] / 2, win[1] - y / 2)):
                    if p[0] < x or p[0] > x + w or p[1] < y or p[1] > y + h:
                        ix, iy = display.window_to_internal(p, win, self.L, mode)
                        self.assertFalse(0 <= ix < 960 and 0 <= iy < 540, (mode, win, p, ix, iy))

    def test_selection_through_both_modes_and_camera_motion(self):
        from systems.targeting import find_target
        from test_v20 import teleport_world
        for mode in display.MODES:
            for win in ((960, 540), (1280, 720), (1536, 864), (1000, 700), (1200, 600)):
                w, inp, e = teleport_world()
                for cam_dx in (0.0, 37.25, 80.0):
                    w.camera.x += cam_dx
                    x, y, _, _, s = display.compute_viewport(win, self.L, mode)
                    sx, sy = w.camera.to_screen(*e.hurtbox.center)
                    win_pos = (x + sx * s, y + sy * s)          # 敵が描かれているウィンドウ上の点
                    internal = display.window_to_internal(win_pos, win, self.L, mode)
                    hit = find_target(w.enemies, w.camera, w.camera.to_world(*internal))
                    self.assertIs(hit, e, (mode, win, cam_dx))
                    # 黒帯（あれば）や空白では選ばれない
                    if x > 1:
                        miss = display.window_to_internal((x / 2, win_pos[1]), win, self.L, mode)
                        self.assertIsNone(find_target(w.enemies, w.camera, w.camera.to_world(*miss)))


class DisplayModeGameTests(unittest.TestCase):
    """作業C: 設定・切替の配線。dummy ドライバには SDL レンダラーが無いため常に Pixel Perfect になる。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "settings.json")

    def test_settings_defaults_and_robust_loading(self):
        s = settings_mod.load(None)
        self.assertEqual((s.display_mode, s.high_dpi), (display.PIXEL_PERFECT, False))
        for raw in ("{broken", "[]", json.dumps({"display_mode": "stretch", "high_dpi": "yes"})):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(raw)
            s = settings_mod.load(self.path)
            self.assertEqual((s.display_mode, s.high_dpi), (display.PIXEL_PERFECT, False), raw)
        s.display_mode, s.high_dpi = display.FIT, True
        self.assertTrue(settings_mod.save(s, self.path))
        s2 = settings_mod.load(self.path)
        self.assertEqual((s2.display_mode, s2.high_dpi), (display.FIT, True))

    def test_sdl_integer_scale_follows_mode(self):
        # dummy ドライバでも SDL のソフトウェアレンダラーがあり、実際の SDL 関数で切り替わる
        import main
        game = main.Game(display_mode=display.FIT)
        if not game.display.supported:
            self.skipTest("SDL renderer unavailable in this environment")
        self.assertEqual(game.display.mode, display.FIT)
        self.assertIs(game.display.integer_scale_enabled(), False)
        self.assertEqual(game.display.toggle(), display.PIXEL_PERFECT)
        self.assertIs(game.display.integer_scale_enabled(), True)
        self.assertEqual(main.Game().display.mode, display.PIXEL_PERFECT)   # 既定は従来どおり
        with self.assertRaises(ValueError):
            game.display.apply("stretch")

    def test_unsupported_renderer_falls_back_to_pixel_perfect(self):
        class NoRenderer(display.DisplayScaler):
            def _bind(self):
                pass
        scaler = NoRenderer()
        self.assertFalse(scaler.supported)
        self.assertEqual(scaler.apply(display.FIT), display.PIXEL_PERFECT)
        self.assertEqual(scaler.toggle(), display.PIXEL_PERFECT)
        self.assertIsNone(scaler.integer_scale_enabled())

    def test_f8_and_pause_menu_toggle_and_save(self):
        import pygame
        import main

        class FakeScaler(display.DisplayScaler):
            def _bind(self):
                self.supported, self.calls = True, []

            def apply(self, mode):
                if mode not in display.MODES:
                    raise ValueError(mode)
                self.calls.append(mode)
                self.mode = mode
                return mode

        game = main.Game(settings_path=self.path)
        game.display = FakeScaler()
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8, mod=0, unicode="", scancode=0))
        self.assertEqual(game.display.mode, display.FIT)
        self.assertEqual(settings_mod.load(self.path).display_mode, display.FIT)
        game.start_play()
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
        self.assertEqual(game.state, main.PAUSED)
        labels = [b.label for b in game.overlay.menu.buttons]
        self.assertIn("表示: Fit to Window", labels)
        btn = game.overlay.menu.buttons[[b.action for b in game.overlay.menu.buttons].index("display")]
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
        self.assertEqual(game.display.mode, display.PIXEL_PERFECT)
        self.assertEqual(game.state, main.PAUSED)          # 切替でポーズは解除されない
        self.assertIn("表示: Pixel Perfect", [b.label for b in game.overlay.menu.buttons])
        self.assertEqual(settings_mod.load(self.path).display_mode, display.PIXEL_PERFECT)
        # F8 はプレイ入力（InputState のアクション）に影響しない
        game._resume()
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8, mod=0, unicode="", scancode=0))
        self.assertFalse(any(game.input.held(a) for a in ("left", "right", "jump", "dash", "teleport")))

    def test_settings_not_written_without_path(self):
        import main
        game = main.Game()
        game.toggle_display_mode()
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
