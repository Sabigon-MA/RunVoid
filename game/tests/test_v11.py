"""v1.1 変更（二段ジャンプ・影這いAI・ヒットストップ）の動作確認。

v2.0: 撃破による空中ダッシュ回復は廃止。ヒットストップは主人公の攻撃がなくなったため、
将来のボス弾・環境攻撃を想定した汎用の攻撃判定で確認する。

    cd game
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_gameplay import (DT, InputState, disable_enemy_attacks, hold_wall,  # noqa: E402
                           make_world, place, settle, step)

from enemies import CrawlerState  # noqa: E402
from systems.combat import RectAttack  # noqa: E402

GROUND = 422.0


def airborne_world(bottom=300.0, x=600.0, enemies=False):
    w = make_world(enemies=enemies)
    hold_wall(w)
    inp = InputState()
    settle(w, inp)
    place(w, x, bottom)
    w.player.on_ground = False
    w.player.coyote = 0.0
    return w, inp


class DoubleJumpTests(unittest.TestCase):
    def _press_jump(self, w, inp):
        inp.simulate_press("jump")
        step(w, inp)

    def test_double_jump_no_triple(self):
        for _ in range(1):
            with self.subTest():
                w = make_world(enemies=False)
                hold_wall(w)
                inp = InputState()
                settle(w, inp)
                p = w.player
                self._press_jump(w, inp)          # 1回目（地上）
                self.assertEqual(p.jumps_used, 1)
                step(w, inp, 20)
                inp.simulate_release("jump")
                step(w, inp)
                self._press_jump(w, inp)          # 2回目（空中）
                self.assertEqual(p.jumps_used, 2)
                self.assertLess(p.vy, -400)
                inp.simulate_release("jump")
                step(w, inp, 5)
                vy_before = p.vy
                self._press_jump(w, inp)          # 3回目は出ない
                self.assertEqual(p.jumps_used, 2)
                self.assertGreater(p.vy, vy_before)   # 重力で増えるだけ

    def test_holding_does_not_auto_double_jump(self):
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        settle(w, inp)
        inp.simulate_press("jump")
        max_used = 0
        for _ in range(120):
            step(w, inp)
            max_used = max(max_used, w.player.jumps_used)
        self.assertEqual(max_used, 1)

    def test_double_jump_resets_fall_speed_and_variable(self):
        w, inp = airborne_world()
        p = w.player
        p.jumps_used = 1
        step(w, inp, 20)
        self.assertGreater(p.vy, 250)            # 落下中
        self._press_jump(w, inp)
        self.assertLess(p.vy, -400)              # 上向きの初速で置き換え
        self.assertTrue(p.jumping)
        inp.simulate_release("jump")
        step(w, inp)
        self.assertGreater(p.vy, -300)           # 早離しで上昇が切られる（可変ジャンプ）

    def test_landing_restores_jumps(self):
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        settle(w, inp)
        self._press_jump(w, inp)
        inp.simulate_release("jump")
        step(w, inp, 3)
        self._press_jump(w, inp)
        inp.simulate_release("jump")
        self.assertEqual(w.player.jumps_used, 2)
        step(w, inp, 120)
        self.assertTrue(w.player.on_ground)
        self.assertEqual(w.player.jumps_used, 0)

    def test_falling_off_ledge_allows_one_air_jump(self):
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        place(w, 760, GROUND)
        settle(w, inp)
        p = w.player
        inp.simulate_press("right")
        while p.on_ground:
            step(w, inp)
        step(w, inp, 10)                          # コヨーテタイム経過後
        inp.simulate_release("right")
        self._press_jump(w, inp)
        self.assertLess(p.vy, 0)                  # 空中で1回は跳べる
        self.assertEqual(p.jumps_used, 2)
        inp.simulate_release("jump")
        step(w, inp, 3)
        vy = p.vy
        self._press_jump(w, inp)
        self.assertGreater(p.vy, vy)              # 2回目の空中ジャンプはない

    def test_coyote_jump_then_one_double_jump(self):
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        place(w, 760, GROUND)
        settle(w, inp)
        p = w.player
        inp.simulate_press("right")
        while p.on_ground:
            step(w, inp)
        step(w, inp, 3)                           # コヨーテタイム内
        self._press_jump(w, inp)
        self.assertEqual(p.jumps_used, 1)         # 地上ジャンプ扱い
        inp.simulate_release("jump")
        step(w, inp, 3)
        self._press_jump(w, inp)
        self.assertEqual(p.jumps_used, 2)

    def test_jump_buffer_after_using_all_jumps(self):
        w, inp = airborne_world(bottom=250)
        p = w.player
        p.jumps_used = 2
        # 着地の数フレーム前にジャンプを押す
        while p.rect.bottom + p.vy * DT * 4 < GROUND:
            step(w, inp)
        self._press_jump(w, inp)
        jumped = False
        for _ in range(8):
            step(w, inp)
            if p.vy < -300:
                jumped = True
                break
        self.assertTrue(jumped)
        self.assertEqual(p.jumps_used, 1)

    def test_double_jump_particles(self):
        w, inp = airborne_world()
        w.player.jumps_used = 1
        before = len(w.effects.particles)
        self._press_jump(w, inp)
        self.assertGreater(len(w.effects.particles), before)


class CrawlerAITests(unittest.TestCase):
    def _setup(self, gap=70):
        w = make_world()
        hold_wall(w)
        w.wall.paused = True
        inp = InputState()
        e = next(e for e in w.enemies if e.enemy_id == "E01")
        e.x = e.home_x = 1150
        place(w, e.x - gap - 12, GROUND)
        settle(w, inp)
        e._enter(CrawlerState.PATROL)   # 準備中に始まった行動をリセット
        return w, inp, e

    def _run_until(self, w, inp, e, state, limit=300):
        for _ in range(limit):
            if e.state == state:
                return
            step(w, inp)
        self.fail(f"{state} にならなかった (現在 {e.state})")

    def test_full_cycle(self):
        w, inp, e = self._setup()
        self._run_until(w, inp, e, CrawlerState.WINDUP)
        x = e.x
        # WINDUP: 0.4秒間完全停止
        frames = 0
        while e.state == CrawlerState.WINDUP:
            self.assertEqual(e.x, x)
            step(w, inp)
            frames += 1
        self.assertEqual(frames, round(0.4 / DT))
        self.assertEqual(e.state, CrawlerState.LUNGE)
        # LUNGE: 0.2秒、240px/s で前方へ
        frames = 0
        while e.state == CrawlerState.LUNGE:
            step(w, inp)
            frames += 1
        self.assertEqual(frames, round(0.2 / DT))
        self.assertAlmostEqual(x - e.x, 240 * 0.2, delta=6)
        # RECOVERY: 0.6秒間水平移動しない
        x = e.x
        frames = 0
        while e.state == CrawlerState.RECOVERY:
            self.assertEqual(e.x, x)
            step(w, inp)
            frames += 1
        self.assertEqual(frames, round(0.6 / DT))
        # COOLDOWN: 0.3秒待機してから再行動
        frames = 0
        while e.state == CrawlerState.COOLDOWN:
            self.assertEqual(e.x, x)
            step(w, inp)
            frames += 1
        self.assertEqual(frames, round(0.3 / DT))
        self.assertIn(e.state, (CrawlerState.CHASE, CrawlerState.PATROL, CrawlerState.WINDUP))

    def test_lunge_direction_locked(self):
        w, inp, e = self._setup()
        self._run_until(w, inp, e, CrawlerState.WINDUP)
        x = e.x
        # 予備動作中にプレイヤーが反対側へ回り込んでも追尾しない
        place(w, e.x + 60, GROUND)
        self._run_until(w, inp, e, CrawlerState.RECOVERY)
        self.assertLess(e.x, x - 40)

    def test_lunge_damage_single_per_frame(self):
        w, inp, e = self._setup()
        p = w.player
        hp_log = [p.hp]
        for _ in range(60):
            step(w, inp)
            hp_log.append(p.hp)
        drops = [a - b for a, b in zip(hp_log, hp_log[1:]) if a != b]
        self.assertGreater(len(drops), 0)
        # 飛びかかり + 接触が重なっても、1フレームで受けるダメージは1回分のみ
        self.assertTrue(all(d == 1 for d in drops), drops)

    def test_lunge_stops_at_cliff(self):
        w = make_world()
        hold_wall(w)
        inp = InputState()
        e = next(e for e in w.enemies if e.enemy_id == "E02")   # G03: 1440〜1824
        e.x = 1790
        place(w, 1830, 420)
        w.player.rect.bottom = 390
        for _ in range(120):
            e.update(DT, w)
            self.assertLessEqual(e.x + e.width / 2, 1824 + 0.1)

    def test_no_attack_when_player_far_above(self):
        w, inp, e = self._setup(gap=40)
        w.player.rect.bottom = 300
        w.player.vy = 0
        e.update(DT, w)
        self.assertNotEqual(e.state, CrawlerState.WINDUP)


class AirDashTests(unittest.TestCase):
    def test_enemy_death_does_not_restore_air_dash(self):
        """v2.0: 敵の消滅で空中ダッシュは回復しない（回復は着地のみ）。"""
        w, inp = airborne_world(enemies=True, x=2000, bottom=200)
        p = w.player
        p.air_dashes_remaining = 0
        e = w.enemies[0]
        w.wall.segments[0].front_x = e.x
        w.wall.paused = True
        step(w, inp)
        self.assertFalse(e.alive)
        self.assertEqual(p.air_dashes_remaining, 0)
        self.assertFalse(hasattr(p, "restore_air_dash"))


class HitstopTests(unittest.TestCase):
    def _hit(self, frames=3):
        w = make_world()
        hold_wall(w)
        w.wall.segments[0].front_x = 0.0
        disable_enemy_attacks(w)
        inp = InputState()
        e = w.enemies[0]
        e.hp = e.max_hp = 1000
        place(w, e.x - e.width / 2 - 34, GROUND)
        w.player.facing = 1
        settle(w, inp)
        # 主人公の攻撃ではなく、汎用の攻撃判定（将来の環境攻撃・ボス弾相当）を敵に当てる
        w.combat.spawn(RectAttack(w.player, 1, 1, 52, 40, 0.0, 0.1, hitstop_frames=frames))
        for _ in range(10):
            step(w, inp)
            if w.in_hitstop:
                return w, inp, e
        self.fail("命中しなかった")

    def test_hitstop_freezes_world(self):
        w, inp, e = self._hit(3)
        self.assertEqual(w.hitstop_frames, 3)
        wall_x, ex, elapsed, px = w.wall.front_x, e.x, w.elapsed, w.player.rect.x
        cd = w.teleport.cooldown_remaining
        inp.simulate_press("right")
        for _ in range(3):
            step(w, inp)
            self.assertEqual(w.wall.front_x, wall_x)   # 追跡壁も止まる
            self.assertEqual(e.x, ex)
            self.assertEqual(w.elapsed, elapsed)
            self.assertEqual(w.player.rect.x, px)
            self.assertEqual(w.teleport.cooldown_remaining, cd)
        self.assertFalse(w.in_hitstop)
        step(w, inp)
        self.assertGreater(w.wall.front_x, wall_x)

    def test_input_during_hitstop_not_lost(self):
        w, inp, e = self._hit()
        inp.simulate_press("jump")
        while w.in_hitstop:
            step(w, inp)
        step(w, inp)
        self.assertLess(w.player.vy, 0)

    def test_knockback_away_from_attacker(self):
        w, inp, e = self._hit()
        x0 = e.x
        step(w, inp, 15)
        self.assertGreater(e.x, x0 + 10)


if __name__ == "__main__":
    unittest.main()
