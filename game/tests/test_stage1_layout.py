"""v2.5 ステージ1（C案）: 城門まわりの自動検証。

    1. 後半の城門（GATE1・GATE2）はテレポートでしか越えられない（通常移動の抜け道がない）
       - 幾何: 城門は主人公が届く最高点より上から、落下死ラインより下まで続く
       - ランダム入力: 壁を止めて時間無制限、左右・ジャンプ・二段・ダッシュ・降下に加えて、
         手前側の敵との交換（誤った相手）も混ぜて試し、城門の左端を越えないこと
       - 敵も城門を越えない（交換相手が門の向こうから手前へ来てしまわない）
    2. 城門の前から、門の向こうの交換相手が見えていて、実際のクリックと同じ入力経路で交換できる
       （既存のテレポート判定 targeting.find_target / TeleportSystem をそのまま使う）
    3. ゲート1の手前の E02（台座の上）は、ゲート1の前からも見えて交換できる（視認性を優先した配置）
    4. 城門の見た目（style="sealed_gate"）は描画だけで、当たり判定は JSON の矩形のまま
"""
from __future__ import annotations

import random
import unittest

from test_gameplay import DT, STAGE_1, InputState, hold_wall, place  # noqa: F401  (SDL dummy 設定を含む)

import pygame

import config
import stage1_bot
from systems.collision import Terrain
from systems.targeting import find_target, is_targetable
from systems.world import CLEAR, PLAYING, World

GATES = stage1_bot.gates(STAGE_1)            # {id: (左端, 右端, 向こうの交換相手)}


def gate_rect(gid):
    return next(p for p in STAGE_1.platforms if p.id == gid)


def wall_free_world(x, bottom=422.0, with_graphics=False):
    """追跡壁を止めた World（時間無制限で試すため）。主人公を (x, bottom) に置きカメラを落ち着かせる。"""
    w = World(STAGE_1, with_graphics=with_graphics)
    hold_wall(w)
    w.wall.paused = True
    place(w, x, bottom)
    for _ in range(120):
        w.camera.follow(w.player.rect, DT)
    return w


def enemy(w, eid):
    return next(e for e in w.enemies if e.enemy_id == eid)


def reach_top():
    """主人公が届く最も高い位置（rect.top の最小値）。地上から長押しジャンプ→頂点で二段ジャンプ→空中ダッシュ。"""
    best = 1e9
    for second in range(10, 50, 2):
        w = wall_free_world(100)
        w.enemies = []
        inp = InputState()
        p = w.player
        for _ in range(10):
            w.update(DT, inp); inp.clear_edges()
        inp.simulate_press("jump")
        for f in range(120):
            if f == second:
                inp.simulate_release("jump"); inp.simulate_press("jump")
            if f == second + 6:
                inp.simulate_press("dash")
            w.update(DT, inp); inp.clear_edges()
            best = min(best, p.rect.top)
    return best


class GateIsImpassableTests(unittest.TestCase):
    """後半でテレポートが必須であること（通常移動の抜け道がない）。"""

    def test_gates_are_full_height_solids(self):
        top = reach_top()
        self.assertGreater(top, 0)                       # 届く最高点でも画面上端（城門の上端 y=0）より下
        for gid in GATES:
            g = gate_rect(gid)
            self.assertLessEqual(g.y, 0)
            self.assertLess(g.y, top - 100)              # 頂上を越える余地はない
            self.assertGreater(g.y + g.h, STAGE_1.kill_y + config.PLAYER_SIZE[1])   # 下をくぐる前に落下死
            self.assertGreaterEqual(g.w, 60)             # 1ステップの最大移動量より十分厚い
        self.assertEqual(STAGE_1.one_way_platforms, ())  # 登るための足場はない
        self.assertLess(gate_rect("GATE2").x + gate_rect("GATE2").w, STAGE_1.goal_x)

    def _fuzz(self, start_x, gid, runs, frames, seed):
        gl = GATES[gid][0]
        rng = random.Random(seed)
        worst = -1e9
        for r in range(runs):
            w = wall_free_world(start_x)
            inp = InputState()
            p = w.player
            held = set()
            for f in range(frames):
                p.hp = p.max_hp if hasattr(p, "max_hp") else 99      # 被弾で終わらせない（押し出しは起きうる）
                if f % rng.choice((1, 2, 3, 5, 8, 13)) == 0:
                    for a, bias in (("right", 0.75), ("left", 0.15), ("jump", 0.35), ("dash", 0.25), ("down", 0.05)):
                        want = rng.random() < bias
                        if want and a not in held:
                            inp.simulate_press(a); held.add(a)
                        elif not want and a in held:
                            inp.simulate_release(a); held.discard(a)
                # 手前側の敵（＝門の向こうの交換相手以外）との交換も混ぜる
                clicked = False
                if w.teleport.ready and rng.random() < 0.05:
                    near = [e for e in w.enemies if is_targetable(e, w.camera) and e.x < gl]
                    if near:
                        stage1_bot.click(w, inp, rng.choice(near)); clicked = True
                if w.update(DT, inp):
                    inp.clear_edges()
                if clicked:
                    stage1_bot.release_click(inp)
                if w.state != PLAYING:
                    break
                worst = max(worst, p.rect.right)
                self.assertLess(p.rect.left, gl, f"{gid}: run {r} frame {f} で城門を越えた")
                self.assertLessEqual(p.rect.right, gl + 1e-6, f"{gid}: run {r} frame {f} で城門にめり込んだ")
        return worst

    def test_random_input_never_passes_gate1(self):
        worst = self._fuzz(1700, "GATE1", runs=120, frames=480, seed=11)
        self.assertGreater(worst, GATES["GATE1"][0] - 5)   # 試験自体は城門まで届いている

    def test_random_input_never_passes_gate2(self):
        # G04（ゲート1の向こう）から: 降り段・穴・G05・ゲート2
        worst = self._fuzz(2450, "GATE2", runs=120, frames=480, seed=22)
        self.assertGreater(worst, GATES["GATE2"][0] - 5)

    def test_no_teleport_runs_stop_at_gate1(self):
        for dash in (True, False):
            for seed in range(6):
                r = stage1_bot.play(STAGE_1, policy="none", dash=dash, jitter=20, seed=seed)
                self.assertNotEqual(r.state, CLEAR)
                self.assertLessEqual(r.world.max_x + config.PLAYER_SIZE[0], GATES["GATE1"][0] + 1e-6)

    def test_enemies_never_cross_a_gate(self):
        lines = [gl for gl, _, _ in GATES.values()]

        def side(x):
            return sum(x >= gl for gl in lines)
        for kw in (dict(policy="required"), dict(policy="required", gate_delay=3.0, gate2_delay=1.0),
                   dict(policy="expert"), dict(policy="required", air_e02=True)):
            r = stage1_bot.play(STAGE_1, record=True, **kw)
            first = {}
            swapped_at = {}
            for i, s in enumerate(r.swaps):
                swapped_at.setdefault(s.target, s.t)
            for step_i, row in enumerate(r.rows):
                t = (step_i + 1) * DT
                for eid, ex, _ in row[9:]:
                    if eid in swapped_at and t >= swapped_at[eid] - 1e-9:
                        continue                     # 交換された敵は主人公のいた側へ移る（交換の仕様）
                    first.setdefault(eid, side(ex))
                    self.assertEqual(side(ex), first[eid], (kw, eid, t))

    def test_only_the_enemy_beyond_the_gate_carries_you_across(self):
        for kw in (dict(policy="required"), dict(policy="expert"), dict(policy="required", air_e02=True),
                   dict(policy="required", wrong_first={"GATE1": "E02"})):
            r = stage1_bot.play(STAGE_1, **kw)
            for s in r.swaps:
                for gid, (gl, gr, tid) in GATES.items():
                    if s.before.right <= gl < s.after.left:
                        self.assertEqual(s.target, tid, kw)


class ClickOverGateTests(unittest.TestCase):
    """城門の前から、門の向こうの交換相手を実際のクリック経路で選べる（既存のテレポート判定）。"""

    def _wait_at_gate(self, gid, seconds=8.0):
        gl, gr, tid = GATES[gid]
        w = wall_free_world(gl - config.PLAYER_SIZE[0])
        inp = InputState()
        frames = []
        hp = w.player.hp
        for _ in range(int(seconds / DT)):
            w.update(DT, inp); inp.clear_edges()
            frames.append(w)
        self.assertEqual(w.player.hp, hp, f"{gid} の前で待っている間に被弾した")
        return w, inp

    def test_target_beyond_each_gate_is_fully_visible_and_unobstructed_every_frame(self):
        # 敵は地形（城門の絵を含む）より後に描かれるので、城門の絵に隠れることはない。ここでは位置と選択を確認する
        for gid, (gl, gr, tid) in GATES.items():
            w = wall_free_world(gl - config.PLAYER_SIZE[0])
            inp = InputState()
            gate = gate_rect(gid).to_rect()
            for f in range(int(8.0 / DT)):
                w.update(DT, inp); inp.clear_edges()
                e = enemy(w, tid)
                view = w.camera.view_rect
                self.assertTrue(is_targetable(e, w.camera), (gid, f))
                self.assertTrue(view.contains(e.hurtbox), (gid, f))            # 画面端で切れていない
                self.assertFalse(gate.colliderect(e.hurtbox), (gid, f))
                self.assertGreaterEqual(e.hurtbox.left, gr, (gid, f))          # 門の向こう側
                self.assertIs(find_target(w.enemies, w.camera, e.hurtbox.center), e, (gid, f))

    def test_real_click_over_each_gate_swaps_across(self):
        for gid, (gl, gr, tid) in GATES.items():
            for wait in (0.0, 2.0, 6.0):
                w = wall_free_world(gl - config.PLAYER_SIZE[0])
                inp = InputState()
                for _ in range(int(wait / DT)):
                    w.update(DT, inp); inp.clear_edges()
                e = enemy(w, tid)
                stage1_bot.click(w, inp, e)                    # MOUSEBUTTONDOWN イベント → InputState
                w.update(DT, inp); inp.clear_edges()
                stage1_bot.release_click(inp)
                self.assertEqual(w.teleport.count, 1, (gid, wait, w.teleport.last_result))
                self.assertGreaterEqual(w.player.rect.left, gr, (gid, wait))
                self.assertLessEqual(e.hurtbox.right, gl + 1e-6, (gid, wait))   # 敵は手前側へ

    def test_target_is_drawn_in_front_of_the_gate_art(self):
        # 実際の描画: 待っている間の各時点で、交換相手の頭上の印（交換可能の色）が描かれている
        tele = tuple(config.COLORS["teleport"])
        for gid, (gl, gr, tid) in GATES.items():
            w = wall_free_world(gl - config.PLAYER_SIZE[0], with_graphics=True)
            inp = InputState()
            s = pygame.Surface((960, 540))
            for f in range(int(6.0 / DT)):
                w.update(DT, inp); inp.clear_edges()
                if f % 30:
                    continue
                w.draw(s)
                box = enemy(w, tid).hurtbox
                x, y = round(box.centerx - w.camera.x), round(box.top - w.camera.y) - 11
                self.assertEqual(tuple(s.get_at((x, y)))[:3], tele, (gid, f))

    def test_click_on_the_gate_itself_selects_nothing(self):
        for gid, (gl, gr, tid) in GATES.items():
            w = wall_free_world(gl - config.PLAYER_SIZE[0])
            for y in range(0, 540, 20):
                self.assertIsNone(find_target(w.enemies, w.camera, ((gl + gr) / 2, y)), (gid, y))

    def test_air_swap_over_each_gate(self):
        # 城門の前で跳び、上昇中・頂点付近・下降中（二段ジャンプも使用）に交換しても越えられる
        for gid, (gl, gr, tid) in GATES.items():
            for when in (8, 25, 45, 70):
                w = wall_free_world(gl - config.PLAYER_SIZE[0])
                inp = InputState()
                p = w.player
                for _ in range(5):
                    w.update(DT, inp); inp.clear_edges()
                inp.simulate_press("jump")
                for f in range(when):
                    if f == 20:
                        inp.simulate_release("jump"); inp.simulate_press("jump")
                    w.update(DT, inp); inp.clear_edges()
                self.assertFalse(p.on_ground)
                stage1_bot.click(w, inp, enemy(w, tid))
                w.update(DT, inp); inp.clear_edges()
                self.assertEqual(w.teleport.count, 1, (gid, when))
                self.assertGreaterEqual(p.rect.left, gr, (gid, when))


class Gate1E02VisibilityTests(unittest.TestCase):
    """ゲート1の手前の E02 は、ゲート1の前からも見えて選べる（視認できる配置を優先）。"""

    def test_e02_visible_and_selectable_from_gate1(self):
        gl = GATES["GATE1"][0]
        w = wall_free_world(gl - config.PLAYER_SIZE[0])
        inp = InputState()
        for f in range(int(8.0 / DT)):
            w.update(DT, inp); inp.clear_edges()
            e2 = enemy(w, "E02")
            self.assertTrue(w.camera.view_rect.contains(e2.hurtbox), f)
            self.assertIs(find_target(w.enemies, w.camera, e2.hurtbox.center), e2, f)
            # 2体の選択範囲は重ならない（どちらを押したかが曖昧にならない）
            from systems.targeting import pick_rect
            self.assertFalse(pick_rect(e2).colliderect(pick_rect(enemy(w, "E03"))), f)

    def test_e02_and_e03_both_have_target_markers_at_gate1(self):
        gl = GATES["GATE1"][0]
        w = wall_free_world(gl - config.PLAYER_SIZE[0], with_graphics=True)
        inp = InputState()
        for _ in range(30):
            w.update(DT, inp); inp.clear_edges()
        s = pygame.Surface((960, 540))
        w.draw(s)
        tele = tuple(config.COLORS["teleport"])
        for eid in ("E02", "E03"):
            box = enemy(w, eid).hurtbox
            x, y = round(box.centerx - w.camera.x), round(box.top - w.camera.y) - 11
            self.assertEqual(tuple(s.get_at((x, y)))[:3], tele, eid)

    def test_misclicking_e02_at_gate1_is_recoverable(self):
        # 誤って後ろの E02 と交換しても、クールダウン明けに E03 と交換すれば（考える時間なしなら）間に合う
        for dash in (True, False):
            r = stage1_bot.play(STAGE_1, policy="required", dash=dash, wrong_first={"GATE1": "E02"})
            self.assertEqual([s.target for s in r.swaps][:2], ["E02", "E03"])
            self.assertEqual(r.state, CLEAR, (dash, r.world.death_cause))


class GateArtIsDrawOnlyTests(unittest.TestCase):
    def test_style_does_not_change_collision(self):
        w = World(STAGE_1, with_graphics=True)
        plain = Terrain([pygame.FRect(p.x, p.y, p.w, p.h) for p in STAGE_1.platforms], [])
        self.assertEqual([tuple(r) for r in w.terrain.solids], [tuple(r) for r in plain.solids])
        for gid in GATES:
            g = gate_rect(gid)
            self.assertEqual(g.style, "sealed_gate")
            self.assertTrue(w.terrain.point_in_solid(g.x + 1, 300))
            self.assertTrue(w.terrain.point_in_solid(g.x + g.w - 1, 600))
            self.assertFalse(w.terrain.point_in_solid(g.x - 1, 300))
            self.assertFalse(w.terrain.point_in_solid(g.x + g.w + 1, 300))

    def test_gate_stone_stays_inside_the_collision_rect(self):
        # 不透明な石は矩形の内側だけ（見えている石の輪郭＝通れない範囲）。外側は細い光の筋のみ
        from stages.renderer import SealedGateArt
        w = World(STAGE_1, with_graphics=True)
        for art in w.terrain_renderer.gates:
            ov = SealedGateArt.OVERHANG
            for y in range(0, art.stone.get_height(), 3):
                for x in list(range(0, ov)) + list(range(art.stone.get_width() - ov, art.stone.get_width())):
                    self.assertEqual(art.stone.get_at((x, y)).a, 0, (art.rect, x, y))

    def test_gate_is_drawn_distinct_from_ground_and_wall(self):
        # 城門の侵食の色は、テレポート色・追跡壁の色と別系統（混同しない）
        w = wall_free_world(GATES["GATE1"][0] - 300, with_graphics=True)
        s = pygame.Surface((960, 540))
        w.terrain_renderer.draw(s, w.camera)
        g = gate_rect("GATE1")
        cols = {tuple(s.get_at((int(g.x - w.camera.x) + dx, y)))[:3]
                for dx in range(2, int(g.w) - 2, 3) for y in range(40, 400, 3)}
        vein = config.COLORS["gate_vein"]
        self.assertTrue(any(c[1] > 150 and c[2] > 150 and c[0] < 140 for c in cols))   # 青緑の光る脈がある
        self.assertGreater(len(cols), 40)                                              # 単色の柱ではない
        for c in ("teleport", "wall_edge", "wall_core"):
            r, gg, b = config.COLORS[c]
            self.assertFalse(abs(r - vein[0]) < 40 and abs(gg - vein[1]) < 40 and abs(b - vein[2]) < 40, c)


if __name__ == "__main__":
    unittest.main()
