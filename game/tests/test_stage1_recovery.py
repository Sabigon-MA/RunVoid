"""ステージ1: 空中交換の後に穴の手前で詰まないこと（地形での救済）。v2.5（C案）の配置。

仕様（v2.2、変更しない）: 二段ジャンプを使い切った空中から交換して地面に着地すると、
その地面を離れるまでジャンプ回数は回復しない。
C案では、どの敵と空中交換しても、着地した地面から次の穴までの間に「降り段」か「台座から降りる地点」があり、
走って降りる＝離地して通常着地することで回復できる:
    E01（G02）→ 降り段 G02s → 穴 1300-1520
    E02（台座 PED）→ 台座から G03 へ降りる → （ゲート1。ジャンプ不要）
    E03（G04）→ 降り段 G04s → 穴 2900-2980 → G05
    E04（G06）→ ゴール（穴なし）
"""
from __future__ import annotations

import unittest

from test_gameplay import DT, STAGE_1, InputState, disable_enemy_attacks, hold_wall, place, step  # noqa: F401

from systems.world import CLEAR, PLAYING, World

# (交換相手, 交換前の主人公の空中位置 (x, bottom), 次の穴の左端, 穴の右端（着地判定）, 降りる段の上面)
CASES = [("E01", (790, 330), 1300, 1520, 438),
         ("E02", (1480, 300), None, None, 422),     # E02 は穴の向こう寄りの上空からしか見えない（設計どおり）
         ("E03", (2200, 300), 2900, 2980, 438),
         ("E04", (2990, 330), None, None, None)]


def air_swap_world(target_id, pos):
    """二段ジャンプ使用済みの空中で target と交換した直後の World を返す。"""
    w = World(STAGE_1, with_graphics=False)
    hold_wall(w)
    disable_enemy_attacks(w)
    w.enemies = [e for e in w.enemies if e.enemy_id == target_id]
    target = w.enemies[0]
    target.speed = 0
    inp = InputState()
    p = w.player
    place(w, *pos)
    p.on_ground, p.jumps_used = False, 2
    for _ in range(90):
        w.camera.follow(p.rect, DT)
    inp.mouse_pos = w.camera.to_screen(*target.hurtbox.center)
    inp.simulate_press("teleport")
    step(w, inp)
    inp.simulate_release("teleport")
    return w, inp


def run_and_jump_pit(w, inp, pit_left, pit_right):
    """右へ走り、穴の手前で（押しっぱなしの）ジャンプをする。穴の向こうに着地したら True。"""
    p = w.player
    inp.simulate_press("right")
    jumped = False
    for _ in range(600):
        if not jumped and p.on_ground and p.rect.right >= pit_left - 15:
            inp.simulate_press("jump")
            jumped = True
        step(w, inp)
        if w.state != PLAYING:
            return w.state == CLEAR
        if p.on_ground and p.rect.left >= pit_right:
            return True
    return False


class AirSwapRecoveryTests(unittest.TestCase):
    def test_swap_landing_keeps_spec(self):
        # 交換着地した地面ではジャンプできない（v2.2 の仕様どおり。今回も変えていない）
        for tid, pos, *_ in CASES:
            w, inp = air_swap_world(tid, pos)
            p = w.player
            self.assertEqual(w.teleport.count, 1, tid)
            for _ in range(60):
                if p.on_ground:
                    break
                step(w, inp)
            self.assertTrue(p.on_ground and p.teleport_grounded, tid)
            self.assertEqual(p.jumps_used, 2, tid)
            inp.simulate_press("jump")
            step(w, inp, 3)
            self.assertTrue(p.on_ground, tid)

    def test_walking_off_restores_jumps_before_the_next_jump_is_needed(self):
        for tid, pos, pit_left, _, below in CASES:
            if below is None:
                continue
            w, inp = air_swap_world(tid, pos)
            p = w.player
            inp.simulate_press("right")
            restored_at = None
            for _ in range(600):
                step(w, inp)
                if p.on_ground and not p.teleport_grounded and p.jumps_used == 0:
                    restored_at = p.rect.right
                    break
            self.assertIsNotNone(restored_at, tid)
            self.assertEqual(p.rect.bottom, below, tid)
            if pit_left is not None:
                self.assertLess(restored_at, pit_left, tid)    # 穴の手前で回復している

    def test_air_swap_then_cross_the_next_pit(self):
        for tid, pos, pit_left, pit_right, _ in CASES:
            if pit_left is None:
                continue
            w, inp = air_swap_world(tid, pos)
            self.assertEqual(w.player.jumps_used, 2)
            self.assertTrue(run_and_jump_pit(w, inp, pit_left, pit_right),
                            f"{tid}: {w.death_cause} x={w.player.rect.x:.0f}")

    def test_air_swap_with_e04_reaches_goal(self):
        w, inp = air_swap_world("E04", CASES[3][1])
        inp.simulate_press("right")
        step(w, inp, 300)
        self.assertEqual(w.state, CLEAR)


if __name__ == "__main__":
    unittest.main()
