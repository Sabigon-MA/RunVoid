"""画像パララックス背景（stages/background.py）の検証。

ウィンドウを開かずに（SDL dummy・set_mode なし）実行できる。
画素の完全一致（ゴールデン画像）ではなく、周期・連続性・被覆・アルファ・カリング・
フォールバック・初期化時のみの読み込みといった性質を確認する。
"""
from __future__ import annotations

import dataclasses
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_gameplay import DT, FIXTURES, InputState, STAGE_1  # noqa: E402

import pygame  # noqa: E402

from stages import background as bgmod  # noqa: E402
from stages import load_stage, parse_stage  # noqa: E402
from stages.background import (BackgroundAssetError, BackgroundConfigError, DecorationLayer,  # noqa: E402
                               ImageLayer, ParallaxImageBackground, PlacementDef, SeamDef,
                               build_background, make_seamless)
from stages.loader import StageFormatError  # noqa: E402
from stages.renderer import TwilightRuinsBackground, make_background  # noqa: E402
from systems.world import PLAYING, World  # noqa: E402

VIEW = (960, 540)
REAL = STAGE_1.background


def minimal_stage(**extra):
    data = {"spawn": {"x": 100, "y": 382}, "platforms": [{"x": 0, "y": 422, "w": 3000, "h": 118}],
            "goal_x": 2900}
    data.update(extra)
    return data


def bg_json(**over):
    raw = {
        "type": "parallax_images",
        "asset_dir": "assets/x",
        "layers": [
            {"id": "sky", "image": "sky.png", "factor": 0.0, "repeat": False},
            {"id": "far", "image": "far.png", "factor": 0.15, "repeat": True,
             "seam": {"mode": "crossfade", "width": 8}},
        ],
    }
    raw.update(over)
    return raw


def rgba_surface(w, h, fn):
    s = pygame.Surface((w, h), pygame.SRCALPHA, 32)
    for x in range(w):
        for y in range(h):
            s.set_at((x, y), fn(x, y))
    return s


def col_diff(surf, xa, xb, step=2):
    """2列の平均絶対差（RGBA, 乗算済み画素のまま比較）。"""
    h = surf.get_height()
    total = 0
    n = 0
    for y in range(0, h, step):
        a, b = surf.get_at((xa, y)), surf.get_at((xb, y))
        total += sum(abs(a[i] - b[i]) for i in range(4))
        n += 1
    return total / (4 * n)


class ConfigTests(unittest.TestCase):
    def test_stage1_declares_four_layers_with_approved_factors(self):
        self.assertIsNotNone(REAL)
        self.assertEqual([l.factor for l in REAL.layers], [0.0, 0.15, 0.40])
        self.assertEqual([l.repeat for l in REAL.layers], [False, True, True])
        self.assertEqual(REAL.decorations.factor, 0.75)
        self.assertTrue(REAL.decorations.placements)

    def test_old_stages_default_to_procedural(self):
        legacy = load_stage(os.path.join(FIXTURES, "legacy_stage.json"))
        self.assertIsNone(legacy.background)
        self.assertIsNone(parse_stage(minimal_stage()).background)
        self.assertIsNone(parse_stage(minimal_stage(background={"type": "procedural"})).background)
        # 既存のデータクラス操作もそのまま使える
        replaced = dataclasses.replace(STAGE_1, background=None)
        self.assertIsNone(replaced.background)
        self.assertEqual(replaced.platforms, STAGE_1.platforms)

    def test_invalid_configs_raise_stage_format_error(self):
        bad = [
            bg_json(type="video"),
            bg_json(asset_dir="/abs/path"),
            bg_json(asset_dir="../outside"),
            bg_json(asset_dir="C:/abs"),
            bg_json(asset_dir=r"assets\..\..\x"),
            bg_json(layers=[]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.2, "repeat": True}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "b", "image": "b.png", "factor": 1.5}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "b", "image": "b.png", "factor": float("nan")}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "b", "image": "b.png", "factor": 0.3, "repeat": False}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "b", "image": "b.png", "factor": 0.3, "seam": {"mode": "mirror"}}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "b", "image": "b.png", "factor": 0.3,
                             "seam": {"mode": "crossfade", "width": 0}}]),
            bg_json(layers=[{"id": "a", "image": "a.png", "factor": 0.0, "repeat": False},
                            {"id": "a", "image": "b.png", "factor": 0.3}]),
            bg_json(decorations={"id": "n", "image": "n.png", "factor": 0.75,
                                 "sprites": {"s": {"src": [0, 0, 10, 10]}},
                                 "placements": [{"sprite": "missing", "x": 0, "bottom": 400}]}),
            bg_json(decorations={"id": "n", "image": "n.png", "factor": 0.75,
                                 "sprites": {"s": {"src": [0, 0, 10]}}, "placements": []}),
            bg_json(decorations={"id": "n", "image": "n.png", "factor": 0.75, "period": 100,
                                 "sprites": {"s": {"src": [0, 0, 10, 10]}},
                                 "placements": [{"sprite": "s", "x": 150, "bottom": 400}]}),
            bg_json(ground_shade={"top": 400, "color": [300, 0, 0]}),
            "not an object",
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(StageFormatError):
                parse_stage(minimal_stage(background=raw))


class WrapTests(unittest.TestCase):
    def layer(self, period=864, factor=0.4):
        return ImageLayer("t", pygame.Surface((period, 4), pygame.SRCALPHA), factor, 0, True, True)

    def test_tiles_cover_view_for_negative_fractional_and_large_cameras(self):
        for factor in (0.15, 0.40):
            lay = self.layer(864, factor)
            for cam in (0.0, 0.3, -0.3, -500.5, 123.75, 2159.999, 2160.0, 2160.001, 1e6 + 0.5,
                        -1e-14, -1e-300, 864 / factor):
                with self.subTest(factor=factor, cam=cam):
                    xs = lay.tile_positions(cam, VIEW[0])
                    self.assertTrue(-864 < xs[0] <= 0)
                    self.assertGreaterEqual(xs[-1] + 864, VIEW[0])
                    self.assertTrue(all(b - a == 864 for a, b in zip(xs, xs[1:])))
                    self.assertLessEqual(len(xs), 3)   # 画面に掛かる枚数だけ

    def test_static_layer_never_moves(self):
        lay = ImageLayer("sky", pygame.Surface(VIEW), 0.0, 0, False, False)
        for cam in (-1000.5, 0, 1234.5):
            self.assertEqual(lay.tile_positions(cam, VIEW[0]), [0])

    def test_each_factor_moves_content_by_factor_times_camera(self):
        """マーカー列の画面位置が camera * factor（周期で折り返し）だけ動く。"""
        period = 200
        for factor in (0.15, 0.40):
            src = pygame.Surface((period, 2), pygame.SRCALPHA)
            src.fill((0, 0, 0, 0))
            src.fill((255, 255, 255, 255), (50, 0, 1, 2))
            lay = ImageLayer("t", src, factor, 0, True, False)
            for cam in (0.0, 100.0, 400.0, -300.0, 1000.0, 77.5):
                target = pygame.Surface((300, 2))
                target.fill((0, 0, 0))
                lay.draw(target, cam)
                lit = [x for x in range(300) if target.get_at((x, 0))[0] > 128]
                expected = {x for x in range(300)
                            if (x - (50 - math.floor(cam * factor % period))) % period == 0}
                with self.subTest(factor=factor, cam=cam):
                    self.assertEqual(set(lit), expected)

    def test_decoration_moves_at_its_factor_and_aligns_at_screen_center(self):
        sprites = {"s": pygame.Surface((20, 10), pygame.SRCALPHA)}
        deco = DecorationLayer("n", sprites, [PlacementDef("s", 1000.0, 400.0)], 0.75, 960, None)
        p = deco.items[0]
        x0, y0 = deco.screen_pos(p, 520.0)        # 配置xが画面中央 → ワールドと同じ位置
        self.assertEqual(x0 + 10, 1000 - 520)
        self.assertEqual(y0, 390)
        x1, _ = deco.screen_pos(p, 520.0 + 100)
        self.assertEqual(x0 - x1, 75)            # カメラ 100px → 75px


class SeamTests(unittest.TestCase):
    def test_crossfade_keeps_interior_and_is_continuous_across_wrap(self):
        w, h, k = 64, 6, 16
        src = rgba_surface(w, h, lambda x, y: (x * 4 % 256, 200, 50 + y * 20, 255 if x < 40 else 120))
        tile = make_seamless(src, SeamDef("crossfade", k))
        premul = src.premul_alpha()
        self.assertEqual(tile.get_width(), w - k)
        for x in range(k, w - k):           # 中央部は原画そのまま
            for y in range(h):
                self.assertEqual(tile.get_at((x, y)), premul.get_at((x, y)))
        for i in range(k):                  # 帯は右端→左端の線形合成
            t = (i + 0.5) / k
            for y in range(h):
                a = premul.get_at((w - k + i, y))
                b = premul.get_at((i, y))
                got = tile.get_at((i, y))
                for c in range(4):
                    self.assertAlmostEqual(got[c], a[c] * (1 - t) + b[c] * t, delta=3)
        # 折り返し: タイル末尾の次はタイル先頭（≒ 原画で末尾の右隣）
        self.assertLess(col_diff(tile, w - k - 1, 0, 1), col_diff(premul, w - k - 1, 0, 1) + 1e-9)

    def test_feather_fades_edges_to_transparent_and_keeps_center(self):
        src = rgba_surface(40, 3, lambda x, y: (200, 100, 50, 255))
        tile = make_seamless(src, SeamDef("feather", 10))
        self.assertEqual(tile.get_width(), 40)
        self.assertLess(tile.get_at((0, 1))[3], 10)
        self.assertLess(tile.get_at((39, 1))[3], 10)
        self.assertEqual(tile.get_at((20, 1)), src.premul_alpha().get_at((20, 1)))

    def test_premultiplied_blit_matches_straight_alpha(self):
        src = rgba_surface(16, 4, lambda x, y: (240, 120 + y * 10, 30, x * 16))
        a = pygame.Surface((16, 4))
        a.fill((20, 60, 90))
        b = a.copy()
        a.blit(src, (0, 0))
        b.blit(make_seamless(src, SeamDef()), (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        for x in range(16):
            for y in range(4):
                for c in range(3):
                    self.assertAlmostEqual(a.get_at((x, y))[c], b.get_at((x, y))[c], delta=2)

    def test_real_layers_wrap_without_hard_edge(self):
        """実素材: 継ぎ目の列差が絵の中の隣接列差と同程度。処理なしでは大きく跳ねることも確認。"""
        bg = ParallaxImageBackground(REAL, *VIEW)
        for lay in bg.layers[1:]:
            tile = lay.surface
            p = tile.get_width()
            inner = sorted(col_diff(tile, x, x + 1) for x in range(100, p - 100, 37))
            typical = inner[len(inner) * 3 // 4]
            seam = col_diff(tile, p - 1, 0)
            with self.subTest(layer=lay.id):
                self.assertLessEqual(seam, typical * 1.5 + 1)
        raw = dataclasses.replace(REAL, layers=tuple(
            dataclasses.replace(l, seam=SeamDef()) for l in REAL.layers), decorations=None)
        hard = ParallaxImageBackground(raw, *VIEW).layers[2].surface
        inner = sorted(col_diff(hard, x, x + 1) for x in range(100, 860, 37))
        self.assertGreater(col_diff(hard, hard.get_width() - 1, 0), inner[len(inner) * 3 // 4] * 3)

    def test_active_material_versions(self):
        """有効な素材は draft_v1 の原画のまま（finish_v2 の候補はすべて不採用）。L1/L2 は crossfade 96。"""
        self.assertEqual(REAL.asset_dir, "assets/backgrounds/twilight_ruins/draft_v1")
        images = [l.image for l in REAL.layers] + [REAL.decorations.image]
        self.assertEqual(images, ["01_sky.png", "02_far_castle.png",
                                  "03_mid_invasion.png", "04_near_debris.png"])
        self.assertEqual(REAL.layers[0].seam, SeamDef())
        self.assertEqual(REAL.layers[1].seam, SeamDef("crossfade", 96))
        self.assertEqual(REAL.layers[2].seam, SeamDef("crossfade", 96))


class RealAssetTests(unittest.TestCase):
    def setUp(self):
        bgmod.clear_cache()

    def test_builds_from_any_cwd_without_display(self):
        self.assertIsNone(pygame.display.get_surface())
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                stage = load_stage("stage_1.json")
                bg = make_background(stage.theme, *VIEW, stage.background)
            finally:
                os.chdir(old)
        self.assertIsInstance(bg, ParallaxImageBackground)
        sky, far, mid = bg.layers
        self.assertEqual(sky.surface.get_size(), VIEW)
        self.assertEqual((far.factor, mid.factor, bg.decorations.factor), (0.15, 0.40, 0.75))
        # 透明な上下は切り詰め済み・アルファは保持
        self.assertGreater(far.y, 0)
        self.assertLess(far.surface.get_height(), VIEW[1])
        self.assertEqual(far.surface.get_at((10, 0))[3] < 255 or far.surface.get_at((800, 0))[3] < 255, True)
        alphas = {mid.surface.get_at((x, mid.surface.get_height() // 2))[3] for x in range(0, 864, 9)}
        self.assertTrue(min(alphas) < 30 and max(alphas) > 200)

    def test_full_screen_is_covered_at_any_camera(self):
        bg = build_background(REAL, *VIEW)
        target = pygame.Surface(VIEW)
        for cam in (-777.25, 0.0, 0.5, 2159.6, 2160.0, 2240.0, 12345.75):
            target.fill((255, 0, 255))
            bg.draw(target, cam)
            for x in range(0, VIEW[0], 7):
                for y in range(0, VIEW[1], 11):
                    self.assertNotEqual(tuple(target.get_at((x, y)))[:3], (255, 0, 255))

    def test_no_loading_or_scaling_after_initialization(self):
        bg = build_background(REAL, *VIEW)
        target = pygame.Surface(VIEW)
        boom = mock.Mock(side_effect=AssertionError("per-frame asset work"))
        with mock.patch("pygame.image.load", boom), \
                mock.patch("pygame.transform.smoothscale", boom), \
                mock.patch("pygame.transform.scale", boom), \
                mock.patch("pygame.transform.flip", boom):
            for i in range(240):
                bg.update(DT)
                bg.draw(target, i * 13.37 - 400)
            # リトライ（World 再生成）でも再読み込みしない
            self.assertIs(build_background(REAL, *VIEW), bg)
        boom.assert_not_called()


class DecorationCullingTests(unittest.TestCase):
    def make(self, period=None):
        sprites = {"a": pygame.Surface((180, 100), pygame.SRCALPHA),
                   "b": pygame.Surface((40, 20), pygame.SRCALPHA)}
        xs = range(0, 3000, 137)
        placements = [PlacementDef("a" if i % 3 else "b", float(x), 450.0) for i, x in enumerate(xs)]
        return DecorationLayer("n", sprites, placements, 0.75, 960, period)

    def brute(self, deco, cam, offsets):
        out = []
        for off in offsets:
            for p in deco.items:
                x, y = deco.screen_pos(p, cam, off)
                if x + deco.sprites[p.sprite].get_width() > 0 and x < 960:
                    out.append((p.sprite, x, y))
        return sorted(out)

    def test_only_on_screen_decorations_are_drawn(self):
        deco = self.make()
        for cam in (-900.0, -12.5, 0.0, 333.3, 1500.0, 2240.0, 5000.0):
            vis = deco.visible(cam)
            with self.subTest(cam=cam):
                self.assertEqual(sorted(vis), self.brute(deco, cam, [0.0]))
                self.assertLess(len(vis), len(deco.items))

        class Counting(pygame.Surface):
            blits = 0

            def blit(self, *a, **k):
                Counting.blits += 1
                return super().blit(*a, **k)

        target = Counting((960, 540))
        deco.draw(target, 1500.0)
        self.assertEqual(Counting.blits, len(deco.visible(1500.0)))

    def test_period_repeats_placements_for_endless_title_scroll(self):
        deco = self.make(period=3000.0)
        for cam in (-5000.25, 0.0, 2999.0, 4100.5, 90000.0):
            vis = deco.visible(cam)
            offsets = [k * 3000.0 for k in range(-40, 41)]
            with self.subTest(cam=cam):
                self.assertTrue(vis)
                self.assertEqual(sorted(vis), self.brute(deco, cam, offsets))


class FallbackTests(unittest.TestCase):
    def setUp(self):
        bgmod.clear_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "assets/x").mkdir(parents=True)
        pygame.image.save(rgba_surface(32, 18, lambda x, y: (90, 40, 40, 255)), str(self.root / "assets/x/sky.png"))
        pygame.image.save(rgba_surface(32, 18, lambda x, y: (200, 200, 200, 255 if y > 9 else 0)),
                          str(self.root / "assets/x/far.png"))
        self.patch = mock.patch.object(bgmod, "GAME_DIR", self.root)
        self.patch.start()
        self.config = parse_stage(minimal_stage(background=bg_json())).background

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()
        bgmod.clear_cache()

    def test_valid_assets_build_image_background(self):
        bg = make_background("twilight_ruins", 96, 54, self.config)
        self.assertIsInstance(bg, ParallaxImageBackground)

    def test_missing_image_falls_back_to_procedural(self):
        (self.root / "assets/x/far.png").unlink()
        with self.assertLogs("runvoid.background", "WARNING"):
            bg = make_background("twilight_ruins", 96, 54, self.config)
        self.assertIsInstance(bg, TwilightRuinsBackground)

    def test_corrupt_image_falls_back_to_procedural(self):
        (self.root / "assets/x/sky.png").write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")
        with self.assertLogs("runvoid.background", "WARNING"):
            bg = make_background("twilight_ruins", 96, 54, self.config)
        self.assertIsInstance(bg, TwilightRuinsBackground)

    def test_unexpected_errors_are_not_swallowed(self):
        with mock.patch("pygame.image.load", side_effect=ValueError("bug")):
            with self.assertRaises(ValueError):
                make_background("twilight_ruins", 96, 54, self.config)
        with self.assertRaises(BackgroundAssetError):
            bgmod.load_image(self.root / "nope.png")

    def test_sprite_outside_image_is_a_config_error(self):
        raw = bg_json(decorations={"id": "n", "image": "far.png", "factor": 0.75,
                                   "sprites": {"s": {"src": [20, 0, 40, 10]}},
                                   "placements": [{"sprite": "s", "x": 0, "bottom": 50}]})
        config = parse_stage(minimal_stage(background=raw)).background
        with self.assertRaises(BackgroundConfigError):
            make_background("twilight_ruins", 96, 54, config)


class GameplayIndependenceTests(unittest.TestCase):
    """背景の有無・種類でプレイ結果（物理・テレポート・敵）が一切変わらないこと。"""

    @staticmethod
    def scripted_run(stage, graphics, frames=900):
        bgmod.clear_cache()
        w = World(stage, with_graphics=graphics)
        inp = InputState()
        surf = pygame.Surface(VIEW) if graphics else None
        trace = []
        inp.simulate_press("right")
        for f in range(frames):
            if f % 45 == 0:
                inp.simulate_press("jump")
            elif f % 45 == 8:
                inp.simulate_release("jump")
            if f % 30 == 0 and w.enemies:
                e = min(w.enemies, key=lambda e: abs(e.hurtbox.centerx - w.player.rect.centerx))
                inp.mouse_pos = w.camera.to_screen(*e.hurtbox.center)
                inp.simulate_press("teleport")
            elif f % 30 == 1:
                inp.simulate_release("teleport")
            if w.update(DT, inp):
                inp.clear_edges()
            if surf is not None:
                w.draw(surf)
            trace.append((round(w.player.rect.x, 6), round(w.player.rect.y, 6), w.player.hp,
                          round(w.camera.x, 6), round(w.teleport.cooldown_remaining, 6),
                          len(w.enemies), w.state))
            if w.state != PLAYING:
                break
        return trace

    def test_trace_identical_with_image_procedural_and_no_graphics(self):
        base = self.scripted_run(STAGE_1, graphics=False)
        self.assertGreater(len(base), 60)
        self.assertEqual(self.scripted_run(STAGE_1, graphics=True), base)
        procedural = dataclasses.replace(STAGE_1, background=None)
        self.assertEqual(self.scripted_run(procedural, graphics=True), base)


if __name__ == "__main__":
    unittest.main()
