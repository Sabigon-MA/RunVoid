"""ステージ1 v3.0（立体マルチルート）と、空を飛ぶ敵「影翔け」の検証。

v3.0 の要点:
    ・stages/stage_1_v3.json（v2.5 の stage_1.json は変更しない）。縦スクロール（camera_bounds −180〜880）。
    ・上層（すり抜け足場の屋根・浮遊遺構）／中層（v2.5 と同じ地形）／地下（地下水路）の3層。
    ・穴は2種類: 「地下への入口」（下に地下の床がある。落ちても死なない）と「落とし穴」（下に何もない。落下死）。
    ・城門 GATE1・GATE2 は全部の層を縦に貫き、テレポートでしか越えられない。
    ・敵は影這い（地上）と影翔け（空中）の2種類。
"""
import json
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from test_gameplay import DT, STAGE_1  # noqa: E402
import config  # noqa: E402
import stage1_bot as bot  # noqa: E402
from enemies import FlierState, ShadowFlier  # noqa: E402
from stages import load_stage, parse_stage  # noqa: E402
from stages.loader import STAGE_DIR, StageFormatError  # noqa: E402
from stages.renderer import PIT_DEATH, PIT_ENTRANCE, TerrainRenderer, classify_pits, find_pits  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.targeting import find_target, is_targetable  # noqa: E402
from systems.world import CLEAR, DEAD, PLAYING, World  # noqa: E402

V3 = load_stage("stage_1_v3.json")

# ボットの踏み切りの表（rect.right の下限, 足場の上面, 二段ジャンプ）
MID = bot.ROUTE                                            # v2.5 と同じ踏み切り
UNDER = [r for r in bot.ROUTE if r[0] != 745]              # 穴 760 を跳ばずに地下へ落ちる
UPPER = [(362, 422, False), (745, 422, False), (960, 422, False), (1040, 302, False),
         (1220, 182, False), (1600, 140, False), (1990, 160, False), (2700, 222, False)]
UPPER_TARGETS = {"GATE1": "EU3", "GATE2": "EU4"}
ROUTES = {"mid": dict(route=MID), "under": dict(route=UNDER, rescue=False),
          "upper": dict(route=UPPER, brakes=[], gate_targets=UPPER_TARGETS)}


def _raw_v3():
    with open(STAGE_DIR / "stage_1_v3.json", encoding="utf-8") as f:
        return json.load(f)


def _plat(stage, pid):
    return next(p for p in list(stage.platforms) + list(stage.one_way_platforms) if p.id == pid)


def _free_world(stage, x, foot_y, graphics=False):
    """追跡壁を止めて、主人公を (x, foot_y) に置いたワールド。"""
    w = World(stage, with_graphics=graphics)
    w.wall.paused = True
    w.wall.segments[0].front_x = -1e5
    w.player.place_foot(x, foot_y)
    w.player.on_ground = False
    w.camera.snap_to(w.player.rect)
    return w


def _run(w, inp, seconds):
    for _ in range(int(round(seconds / DT))):
        if w.update(DT, inp):
            inp.clear_edges()
        if w.state != PLAYING:
            break


# ---------------------------------------------------------------------------
class CompatibilityTests(unittest.TestCase):
    """v2.5 とテスト用ステージは縦スクロールなし（今までと同じ）。"""

    def test_v25_has_no_vertical_camera(self):
        self.assertIsNone(STAGE_1.camera_bounds)
        self.assertFalse(STAGE_1.vertical)
        r = bot.play(STAGE_1, policy="required", record=True)
        self.assertEqual(r.state, CLEAR)
        self.assertEqual(r.world.camera.y, 0.0)

    def test_v25_file_is_unchanged_by_v3(self):
        self.assertEqual(len(STAGE_1.platforms), 13)
        self.assertEqual(len(STAGE_1.one_way_platforms), 0)
        self.assertEqual({e.type for e in STAGE_1.enemies}, {"shadow_crawler"})

    def test_background_draw_without_offset_is_identical(self):
        w = World(STAGE_1)
        for cx in (0.0, 700.0, 2400.0):
            a, b = pygame.Surface((960, 540)), pygame.Surface((960, 540))
            w.background.draw(a, cx)
            w.background.draw(b, cx, 0.0)
            self.assertEqual(pygame.image.tobytes(a, "RGB"), pygame.image.tobytes(b, "RGB"))

    def test_find_pits_of_v25_unchanged(self):
        rects = [p.to_rect() for p in STAGE_1.platforms]
        self.assertEqual(find_pits(rects, STAGE_1.world_width, 540),
                         [(760, 870, 422), (1300, 1520, 422), (2900, 2980, 422)])
        self.assertEqual(classify_pits(rects, find_pits(rects, STAGE_1.world_width, 540), 540), [PIT_DEATH] * 3)


class LoaderTests(unittest.TestCase):
    def test_v3_values(self):
        self.assertEqual(V3.camera_bounds, (-180.0, 880.0))
        self.assertEqual(V3.kill_y, 944.0)
        self.assertEqual((V3.goal_x, V3.world_width), (3200.0, 3360.0))
        self.assertEqual(V3.checkpoint.x, 1560.0)
        self.assertEqual({e.type for e in V3.enemies}, {"shadow_crawler", "shadow_flier"})

    def test_bounds_validation(self):
        for bounds, kill in (({"top": 0, "bottom": 400}, None), ({"top": 100, "bottom": 900}, None),
                             ({"top": -180, "bottom": 500}, None), ({"top": -180, "bottom": 880}, 700)):
            raw = _raw_v3()
            raw["camera_bounds"] = bounds
            if kill is not None:
                raw["kill_y"] = kill
            with self.assertRaises(StageFormatError, msg=str(bounds)):
                parse_stage(raw)


class GeometryTests(unittest.TestCase):
    JUMP1, JUMP2 = 144.3, 288.5      # 実測（stages/stage1_v3_design/jump_probe.py）

    def test_gates_seal_every_layer(self):
        top_reach = min(p.y for p in V3.one_way_platforms) - self.JUMP2
        for gid in ("GATE1", "GATE2"):
            g = _plat(V3, gid)
            self.assertEqual(g.style, "sealed_gate")
            self.assertLessEqual(g.y, top_reach - 100, gid)              # 上層から届く最高点より 100px 以上上
            self.assertLess(g.y, V3.camera_bounds[0])
            self.assertGreaterEqual(g.y + g.h, V3.kill_y + config.PLAYER_SIZE[1], gid)
        for p in V3.one_way_platforms:                                   # 城門をまたぐすり抜け足場はない
            for gid in ("GATE1", "GATE2"):
                g = _plat(V3, gid)
                self.assertFalse(p.x < g.x + g.w and p.x + p.w > g.x, (p.id, gid))

    def test_mid_route_arcs_cannot_land_on_upper_layer(self):
        """中層の通常の跳躍（地面から一段、G02s から二段）の頂点は、その上にある上層の足場に届かない。"""
        self.assertGreater(_plat(V3, "R1").y, 0)
        self.assertLess(_plat(V3, "R1").y, 422 - self.JUMP1)             # G01 からの一段では乗れない
        self.assertLess(_plat(V3, "U2").y, 438 - self.JUMP2)             # G02s からの二段では乗れない
        # U3 は二段ジャンプの頂点より先にあり、下降中に下を通り抜ける。実際の軌跡で確認する
        for dash in (False, True):
            r = bot.play(V3, policy="required", dash=dash, record=True)
            feet = [row[1] + config.PLAYER_SIZE[1] for row in r.rows if row[6]]   # 接地しているときの足元
            self.assertGreater(min(feet), 300, dash)                       # 中層ルートは一度も上層に乗らない

    def test_designed_links_are_reachable(self):
        links = [("S01", "R1", 1), ("R1", "U1", 1), ("B01", "U1", 1), ("U1", "U2", 1), ("U2", "U3", 1),
                 ("U3", "U4", 1), ("PED", "U3", 2), ("U5", "U6", 1), ("D1", "ST1", 1), ("ST1", "ST2", 1),
                 ("ST2", "G03", 1)]
        for a, b, n in links:
            rise = _plat(V3, a).y - _plat(V3, b).y
            self.assertLessEqual(rise, (self.JUMP1 if n == 1 else self.JUMP2) - 20, (a, b))

    def test_underground_headroom(self):
        d1 = _plat(V3, "D1")
        self.assertGreaterEqual(d1.y - 540, self.JUMP1 + config.PLAYER_SIZE[1] + 10)


class PitPatternTests(unittest.TestCase):
    """穴の2パターン: 地下への入口（落ちても地下へ）と落とし穴（落下死）。"""

    def setUp(self):
        self.r = TerrainRenderer(V3)

    def test_classification(self):
        got = {(x0, x1): k for (x0, x1, _), k in zip(self.r.pits, self.r.pit_kinds)}
        self.assertEqual(got, {(760, 870): PIT_ENTRANCE, (1300, 1450): PIT_ENTRANCE, (2900, 2980): PIT_DEATH})

    def test_entrance_and_death_pit_look_different(self):
        """入口は底が青緑、落とし穴は底が赤。"""
        def bottom_color(kind):
            img = next(img for (_, _, img), k in zip(self.r.pit_images, self.r.pit_kinds) if k == kind)
            return img.get_at((img.get_width() // 2, img.get_height() - 2))
        ent, dth = bottom_color(PIT_ENTRANCE), bottom_color(PIT_DEATH)
        self.assertGreater(ent.g, ent.r + 30)
        self.assertGreater(dth.r, dth.g + 30)

    def _drop(self, x):
        w = _free_world(V3, x, 422)
        w.player.on_ground = True
        inp = InputState()
        _run(w, inp, 2.0)
        return w

    def test_falling_into_entrance_survives(self):
        for x in (815, 1330):
            w = self._drop(x)
            self.assertEqual(w.state, PLAYING, x)
            self.assertTrue(w.player.on_ground)
            self.assertGreater(w.player.rect.bottom, 540, x)            # 地下（または竪穴の階段）に着地

    def test_falling_into_death_pit_kills(self):
        w = self._drop(2940)
        self.assertEqual((w.state, w.death_cause), (DEAD, "fall"))


class CameraTests(unittest.TestCase):
    def test_follows_into_underground_and_clamps(self):
        w = _free_world(V3, 815, 422)
        _run(w, InputState(), 2.0)
        self.assertEqual(w.camera.y, V3.camera_bounds[1] - 540)          # 下限で止まる
        self.assertTrue(w.camera.view_rect.contains(w.player.rect))

    def test_jumping_on_flat_ground_does_not_move_camera_vertically(self):
        w = _free_world(V3, 300, 422)
        _run(w, InputState(), 0.5)
        y0 = w.camera.y
        inp = InputState(); inp.simulate_press("jump")
        ys = []
        for _ in range(50):
            w.update(DT, inp); inp.clear_edges(); ys.append(w.camera.y)
        self.assertLess(max(abs(y - y0) for y in ys), 1.0)

    def test_upper_layer_shows_middle_enemies(self):
        """上層 U1 に立つと中層の E01 が、中層 G02 に立つと上層の EU1 が、全身画面に入る（カメラ規則 0.53）。"""
        for plat, x, eid in (("U1", 1000, "E01"), ("G02", 900, "EU1")):
            w = _free_world(V3, x, _plat(V3, plat).y)
            _run(w, InputState(), 1.5)
            e = next(e for e in w.enemies if e.enemy_id == eid)
            self.assertTrue(w.camera.view_rect.contains(e.hurtbox), (plat, eid))
            self.assertTrue(is_targetable(e, w.camera))

    def test_vertically_offscreen_enemy_is_not_selectable(self):
        w = _free_world(V3, 1000, 742)                                   # 地下 D1
        _run(w, InputState(), 1.0)
        eu1 = next(e for e in w.enemies if e.enemy_id == "EU1")
        self.assertFalse(w.camera.view_rect.colliderect(eu1.hurtbox))
        self.assertFalse(is_targetable(eu1, w.camera))
        self.assertIsNone(find_target(w.enemies, w.camera, eu1.hurtbox.center))
        e01 = next(e for e in w.enemies if e.enemy_id == "E01")           # 中層の E01 は地下から見えて選べる
        self.assertTrue(is_targetable(e01, w.camera))


class RouteTests(unittest.TestCase):
    """ボットによるルートごとの検証（ダッシュなし／あり）。"""

    def test_no_teleport_cannot_pass_gate1(self):
        for name, kw in ROUTES.items():
            for dash in (False, True):
                r = bot.play(V3, policy="none", dash=dash, **kw)
                self.assertEqual((r.state, r.world.death_cause), (DEAD, "wall"), (name, dash))
                self.assertLess(r.world.player.rect.right, _plat(V3, "GATE1").x + 1, (name, dash))

    def test_every_route_clears_with_required_swaps(self):
        for name, kw in ROUTES.items():
            for dash in (False, True):
                r = bot.play(V3, policy="required", dash=dash, gate_delay=1.0, **kw)
                self.assertEqual(r.state, CLEAR, (name, dash))
                self.assertEqual(len(r.swaps), 2, (name, dash))

    def test_wall_distance_at_gate1_is_fair(self):
        gaps = {}
        for name, kw in ROUTES.items():
            r = bot.play(V3, policy="required", dash=False, **kw)
            gaps[name] = r.arrive["GATE1"][1]
            self.assertGreaterEqual(gaps[name], 450, name)                # どのルートでも 1.5 秒以上
        ref = bot.play(STAGE_1, policy="required", dash=False).arrive["GATE1"][1]
        self.assertAlmostEqual(gaps["mid"], ref, delta=1.0)               # 中層は v2.5 と同じ
        self.assertGreater(gaps["upper"], gaps["mid"])                     # 上層は速い
        self.assertLess(gaps["under"], gaps["mid"])                        # 地下は遠回り

    def test_routes_are_robust_to_takeoff_jitter(self):
        """踏み切り ±20px のばらつき（30通り）、各城門で1秒考える。中層・地下は全件クリア。

        上層はダッシュなしだと、幅60の B01 に乗り損ねて中層・地下へ回る場合がある（ボットの精度の問題。
        100通りの実測で 88/100、失敗は全部その後に城門で1秒ずつ考えて壁に追いつかれたもの）。ここでは 8 割以上を確認する。
        """
        for name, kw in ROUTES.items():
            for dash in (False, True):
                ok = sum(bot.play(V3, policy="required", dash=dash, gate_delay=1.0, jitter=20, seed=s, **kw).state == CLEAR
                         for s in range(30))
                if name == "upper" and not dash:
                    self.assertGreaterEqual(ok, 24, (name, dash))
                else:
                    self.assertEqual(ok, 30, (name, dash))

    def test_underground_route_recovers_to_ground(self):
        r = bot.play(V3, policy="required", dash=False, route=UNDER, rescue=False, record=True)
        ys = [row[1] + config.PLAYER_SIZE[1] for row in r.rows]
        self.assertTrue(any(y >= 742 - 1 for y in ys))                    # 地下 D1 を通った
        self.assertEqual(r.state, CLEAR)

    def test_upper_route_uses_upper_layer(self):
        r = bot.play(V3, policy="required", dash=False, record=True, **ROUTES["upper"])
        self.assertEqual([s.target for s in r.swaps], ["EU3", "EU4"])
        feet = [row[1] + config.PLAYER_SIZE[1] for row in r.rows if 1300 <= row[0] <= 2200]
        self.assertTrue(feet)
        self.assertLessEqual(max(feet), 300)                               # 竪穴の上でも中層・地下へ落ちない

    def test_checkpoint_works_from_underground(self):
        r = bot.play(V3, policy="none", dash=False, route=UNDER, rescue=False)
        self.assertTrue(r.world.passed_checkpoint)                        # 地下ルートでも x=1,560 で有効
        c = World(V3, with_graphics=False, from_checkpoint=True)
        self.assertEqual(c.player.rect.topleft, (1560, 382))
        _run(c, InputState(), 0.5)
        self.assertTrue(c.player.on_ground)                                # 中層 G03 の上で再開
        self.assertEqual(c.player.rect.bottom, 422)


class FlierTests(unittest.TestCase):
    """影翔け（空を飛ぶ敵）。"""

    RAW = {"spawn": {"x": 100, "y": 382}, "goal_x": 3000, "world_width": 3000,
           "wall": {"start_x": -99999, "speed": 0},
           "platforms": [{"id": "G", "x": 0, "y": 422, "w": 600, "h": 118},
                         {"id": "G2", "x": 900, "y": 422, "w": 2100, "h": 118}],
           "enemies": [{"id": "F", "type": "shadow_flier", "x": 750, "foot_y": 250}]}

    def _world(self, px=100):
        w = World(parse_stage(self.RAW), with_graphics=False)
        w.player.place_foot(px, 422)
        w.camera.snap_to(w.player.rect)
        return w, w.enemies[0]

    def test_hovers_over_void_without_falling(self):
        w, f = self._world()
        self.assertIsInstance(f, ShadowFlier)
        _run(w, InputState(), 3.0)
        self.assertTrue(f.alive)
        self.assertEqual(f.foot_y, 250)
        self.assertFalse(f.airborne)
        self.assertLessEqual(abs(f.x - 750), f.patrol_range + 1)

    def test_swoops_at_player_below_and_returns(self):
        w, f = self._world(px=560)                                         # 地面 G（0〜600）の右端に立つ
        states, max_foot, hit = [], -1e9, False
        hp0 = w.player.hp
        for _ in range(int(4.0 / DT)):
            w.update(DT, InputState())
            states.append(f.state)
            max_foot = max(max_foot, f.foot_y)
            hit = hit or w.player.hp < hp0
        self.assertIn(FlierState.WINDUP, states)
        self.assertIn(FlierState.SWOOP, states)
        self.assertGreater(max_foot, 250 + 50)                             # 実際に降下した
        self.assertLessEqual(max_foot, 422 + 0.01)                         # 地面にめり込まない
        self.assertTrue(hit)                                               # 動かない主人公には当たる
        self.assertIn(FlierState.RETURN, states)
        self.assertAlmostEqual(f.foot_y, 250, delta=1)                     # 元の高さへ戻る

    def test_swoop_stops_at_terrain(self):
        w, f = self._world(px=700)
        w.player.invuln = 99
        bottoms = []
        for _ in range(int(3.0 / DT)):
            w.update(DT, InputState())
            bottoms.append(f.body_rect.bottom)
            self.assertFalse(w.terrain.overlaps_solid(f.body_rect.inflate(-2, -2)))
        self.assertLessEqual(max(bottoms), 422 + 0.01)

    def test_windup_gives_warning_time(self):
        p = config.ENEMIES["shadow_flier"]
        self.assertGreaterEqual(p["windup_time"], 0.4)

    def test_teleport_swap_places_player_in_the_air(self):
        w, f = self._world(px=500)
        inp = InputState()
        pos = w.camera.to_screen(*f.hurtbox.center)
        inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        w.update(DT, inp); inp.clear_edges()
        self.assertEqual(w.teleport.count, 1)
        self.assertAlmostEqual(w.player.rect.bottom, 250, delta=1)        # 主人公は空中へ
        self.assertFalse(w.player.on_ground)
        self.assertAlmostEqual(f.foot_y, 422, delta=1)                    # 影翔けは主人公のいた位置
        self.assertEqual(f.home_y, 422)                                    # 交換後の位置が新しい基準
        self.assertAlmostEqual(f.home_x, 500, delta=1)
        # 交換先は穴（600〜900）の上空なので主人公は落ちていく。影翔けは地面の上を飛び、落ちない
        _run(w, InputState(), 0.3)
        self.assertGreater(w.player.vy, 0)
        self.assertAlmostEqual(f.foot_y, 422, delta=1)

    def test_player_falls_after_swap_over_void_and_can_air_jump(self):
        """穴の上空の影翔けと交換すると空中に出る。地上から交換した場合は空中ジャンプが1回残る（既存の仕様）。"""
        w, f = self._world(px=560)
        pos = w.camera.to_screen(*f.hurtbox.center)
        inp = InputState()
        inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        w.update(DT, inp); inp.clear_edges()
        self.assertLess(w.player.jumps_used, w.player.max_jumps)

    def test_wall_kills_flier_but_falling_does_not(self):
        w, f = self._world(px=1000)                                        # 主人公は壁より前
        _run(w, InputState(), 2.0)
        self.assertTrue(f.alive)                                           # 穴の上空でも落ちて死なない
        w.wall.segments[0].front_x = f.x + 100
        w.update(DT, InputState())
        self.assertEqual(w.state, PLAYING)
        self.assertFalse(f.alive)
        self.assertEqual(f.death_cause, "wall")

    def test_stage_fliers_are_drawn_and_targetable(self):
        for fid in ("F1", "F2", "F3"):
            e = next(e for e in V3.enemies if e.id == fid)
            w = _free_world(V3, e.x - 250, 422 if fid != "F2" else 160, graphics=True)
            _run(w, InputState(), 1.0)
            f = next(x for x in w.enemies if x.enemy_id == fid)
            self.assertTrue(is_targetable(f, w.camera), fid)
            s = pygame.Surface((960, 540))
            w.draw(s)


class RescueTests(unittest.TestCase):
    def test_falling_into_death_pit_can_be_rescued_by_flier(self):
        """落とし穴に落ちても、テレポートが使えれば上空の影翔け F3 と交換して助かる。"""
        w = _free_world(V3, 2940, 470)
        w.player.vy = 300
        f3 = next(e for e in w.enemies if e.enemy_id == "F3")
        inp = InputState()
        w.update(DT, inp); inp.clear_edges()
        pos = w.camera.to_screen(*f3.hurtbox.center)
        inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        w.update(DT, inp); inp.clear_edges()
        self.assertEqual(w.teleport.count, 1)
        inp.simulate_press("left")
        _run(w, inp, 1.5)
        self.assertEqual(w.state, PLAYING)
        self.assertTrue(w.player.on_ground)


class RenderSmokeTests(unittest.TestCase):
    def test_draw_at_vertical_extremes(self):
        w = World(V3)
        s = pygame.Surface((960, 540))
        for cx, cy in ((0, -180), (700, 340), (1200, 340), (2300, -180), (2400, 100)):
            w.camera.x, w.camera.y = cx, cy
            w.draw(s)
        # 地下が見えているとき、画面の下側は地中・地下の色（空の色ではない）
        w.camera.x, w.camera.y = 900, 340
        w.draw(s)
        r, g, b, _ = s.get_at((480, 520))
        self.assertLess(r + g + b, 200)


if __name__ == "__main__":
    unittest.main()
