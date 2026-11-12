"""v1.2 変更（雑魚敵の怯み・被弾後無敵0.3秒）の動作確認。

v2.0: 主人公は直接攻撃できないため、怯みは通常プレイでは発生しない。
共通処理（enemies/base.py）は将来の環境攻撃用に残しているので、汎用の攻撃判定で確認する。

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

import config  # noqa: E402
from enemies import CrawlerState  # noqa: E402
from systems.combat import AttachedAttack, RectAttack  # noqa: E402
from systems.world import DEAD  # noqa: E402

GROUND = 422.0


def setup(gap=70, attacks=True):
    """E01 を x=1150 に置き、プレイヤーを左側 gap px に置く。"""
    w = make_world()
    hold_wall(w)
    w.wall.paused = True
    if not attacks:
        disable_enemy_attacks(w)
    inp = InputState()
    e = next(e for e in w.enemies if e.enemy_id == "E01")
    e.x = e.home_x = 1150
    e.hp = e.max_hp = 1000
    place(w, e.x - gap - 12, GROUND)
    settle(w, inp)
    e._enter(CrawlerState.PATROL)
    e.attack_lock = 0.0
    return w, inp, e


def hit(w, e, stagger, damage=1):
    """攻撃が命中した状態を再現する（CombatSystem と同じ呼び出し）。"""
    attack = RectAttack(w.player, damage, 1, 52, 40, 0, 0.1, stagger_duration=stagger)
    killed = e.take_damage(damage, attack)
    w._on_hit(attack, e, killed)
    return attack


def run_until(w, inp, e, state, limit=300):
    for _ in range(limit):
        if e.state == state:
            return
        step(w, inp)
    raise AssertionError(f"{state} にならなかった (現在 {e.state})")


def lunge_attacks(w):
    return [a for a in w.combat.attacks if isinstance(a, AttachedAttack)]


class StaggerTests(unittest.TestCase):
    def test_stagger_stops_movement_and_attacks(self):
        w, inp, e = setup(gap=200)   # 攻撃範囲外で追跡中
        step(w, inp, 5)
        self.assertEqual(e.state, CrawlerState.CHASE)
        hit(w, e, 0.25)
        self.assertEqual(e.state, CrawlerState.STAGGER)
        # ノックバックが終わった後は、怯みが終わるまで一切動かない
        step(w, inp, round(config.ENEMIES["shadow_crawler"]["knockback_time"] / DT) + 1)
        x = e.x
        place(w, e.x - 60, GROUND)   # 攻撃範囲内に入っても攻撃しない
        while e.state == CrawlerState.STAGGER:
            self.assertEqual(e.x, x)
            self.assertEqual(lunge_attacks(w), [])
            step(w, inp)

    def test_stagger_duration_and_return_to_ai(self):
        w, inp, e = setup(gap=200)
        hit(w, e, 0.25)
        frames = 0
        while e.state == CrawlerState.STAGGER:
            step(w, inp)
            frames += 1
        self.assertEqual(frames, round(0.25 / DT))
        self.assertIn(e.state, (CrawlerState.CHASE, CrawlerState.PATROL))

    def test_windup_interrupted(self):
        w, inp, e = setup()
        run_until(w, inp, e, CrawlerState.WINDUP)
        step(w, inp, 5)
        hit(w, e, 0.15)
        self.assertEqual(e.state, CrawlerState.STAGGER)
        # 怯み明けに飛びかかりが自動再開されない
        while e.state == CrawlerState.STAGGER:
            step(w, inp)
        self.assertNotEqual(e.state, CrawlerState.LUNGE)
        self.assertIn(e.state, (CrawlerState.CHASE, CrawlerState.PATROL, CrawlerState.WINDUP))
        if e.state == CrawlerState.WINDUP:
            self.assertLess(e.state_time, DT * 1.5)   # 新しい予備動作は最初から

    def test_lunge_interrupted_and_hitbox_removed(self):
        w, inp, e = setup(gap=85)
        p = w.player
        run_until(w, inp, e, CrawlerState.LUNGE)
        self.assertEqual(len(lunge_attacks(w)), 1)
        hp = p.hp
        hit(w, e, 0.25)
        self.assertEqual(e.state, CrawlerState.STAGGER)
        x = e.x
        step(w, inp)
        self.assertEqual(lunge_attacks(w), [])      # 攻撃判定が残留しない
        disable_enemy_attacks(w)
        for _ in range(30):
            step(w, inp)
            if e.state != CrawlerState.STAGGER:
                break
        self.assertEqual(p.hp, hp)                  # 中断された飛びかかりでは被弾しない
        self.assertGreaterEqual(e.x, x)             # 突進方向（左）へ進まない

    def test_damage_during_stagger_and_refresh(self):
        w, inp, e = setup(gap=200)
        hit(w, e, 0.25, damage=5)
        step(w, inp, 10)
        remaining = e.stagger_timer
        hp = e.hp
        hit(w, e, 0.25, damage=5)
        self.assertEqual(e.hp, hp - 5)                       # 怯み中もダメージを受ける
        self.assertGreater(e.stagger_timer, remaining)       # 怯み時間が更新される
        self.assertAlmostEqual(e.stagger_timer, 0.25)
        self.assertEqual(e.state, CrawlerState.STAGGER)
        # 短い怯みで長い残り時間を縮めない
        hit(w, e, 0.15)
        self.assertAlmostEqual(e.stagger_timer, 0.25)

    def test_continuous_stagger_lock(self):
        """連続した攻撃で怯みを継続できる（雑魚敵は耐性0）。"""
        w, inp, e = setup(gap=200)
        for _ in range(10):
            hit(w, e, 0.15)
            step(w, inp, round(0.12 / DT))
            self.assertEqual(e.state, CrawlerState.STAGGER)

    def test_contact_damage_during_stagger(self):
        w, inp, e = setup(gap=200)
        hit(w, e, 0.5)
        step(w, inp, 10)
        p = w.player
        place(w, e.x - 12, GROUND)
        hp = p.hp
        step(w, inp)
        self.assertEqual(p.hp, hp - 1)

    def test_no_early_attack_after_stagger_in_recovery(self):
        w, inp, e = setup(gap=85)
        run_until(w, inp, e, CrawlerState.RECOVERY)
        w.player.invuln = 100   # 接触で被弾しないようにする
        hit(w, e, 0.15)
        frames = 0
        while e.state != CrawlerState.WINDUP and frames < 120:
            step(w, inp)
            frames += 1
        # 硬直0.6 + 待機0.3 秒が経過するまで次の攻撃に入らない
        self.assertGreaterEqual(frames * DT, 0.9 - 0.05)

    def test_knockback_does_not_pass_terrain(self):
        w = make_world()
        hold_wall(w)
        disable_enemy_attacks(w)
        inp = InputState()
        e = next(e for e in w.enemies if e.enemy_id == "E02")   # G03: 1440〜1824
        e.hp = e.max_hp = 1000
        e.x = 1824 - e.width / 2 - 2
        place(w, e.x - 60, 390)
        for _ in range(5):
            hit(w, e, 0.25)
            step(w, inp, 10)
            self.assertLessEqual(e.x + e.width / 2, 1824 + 0.1)
        e2 = next(e for e in w.enemies if e.enemy_id == "E01")  # G02 右端は G03 の段差
        e2.hp = e2.max_hp = 1000
        e2.x = 1440 - e2.width / 2 - 2
        place(w, e2.x - 60, GROUND)
        for _ in range(5):
            hit(w, e2, 0.25)
            step(w, inp, 10)
            self.assertLessEqual(e2.x + e2.width / 2, 1440 + 0.1)

    def test_resistance_and_immunity(self):
        w, inp, e = setup(gap=200)
        e.stagger_resistance = 0.5
        hit(w, e, 0.4)
        self.assertAlmostEqual(e.stagger_timer, 0.2)
        e.stagger_timer = 0
        e._enter(CrawlerState.CHASE)
        e.stagger_immunity = True
        hp = e.hp
        hit(w, e, 0.4, damage=3)
        self.assertEqual(e.hp, hp - 3)
        self.assertEqual(e.stagger_timer, 0)
        self.assertNotEqual(e.state, CrawlerState.STAGGER)

    def test_shadow_crawler_defaults(self):
        w, inp, e = setup()
        self.assertEqual(e.stagger_resistance, 0.0)
        self.assertFalse(e.stagger_immunity)

    def test_wall_consumes_staggered_enemy(self):
        w, inp, e = setup(gap=200)
        hit(w, e, 0.5)
        place(w, 2000, GROUND)
        w.wall.segments[0].front_x = e.x
        step(w, inp)
        self.assertFalse(e.alive)
        self.assertEqual(e.death_cause, "wall")

    def test_impact_effects(self):
        w, inp, e = setup(gap=200)
        hit(w, e, 0.25)
        self.assertGreater(e.hurt_flash, 0)
        self.assertGreater(len(w.effects.rings), 0)
        self.assertNotEqual(e.knockback_timer, 0)


class InvulnerabilityTests(unittest.TestCase):
    def test_invuln_is_0_3_seconds(self):
        self.assertEqual(config.PROTAGONIST["stats"]["invuln_time"], 0.3)

    def test_multiple_enemies_same_frame_single_damage(self):
        w = make_world()
        hold_wall(w)
        disable_enemy_attacks(w)
        inp = InputState()
        e1, e2 = w.enemies[0], w.enemies[1]
        e1.speed = e2.speed = 0
        e2.x, e2.foot_y = e1.x + 4, e1.foot_y
        place(w, e1.x - 12, GROUND)
        p = w.player
        hp = p.hp
        step(w, inp)
        self.assertEqual(p.hp, hp - 1)

    def test_lunge_and_contact_same_frame(self):
        w, inp, e = setup(gap=85)
        p = w.player
        log = [p.hp]
        for _ in range(90):
            step(w, inp)
            log.append(p.hp)
        drops = [a - b for a, b in zip(log, log[1:]) if a != b]
        self.assertTrue(drops)
        self.assertTrue(all(d == 1 for d in drops), drops)

    def test_can_act_while_invulnerable(self):
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        settle(w, inp)
        p = w.player
        p.take_damage(1)
        self.assertGreater(p.invuln, 0)
        x = p.rect.x
        inp.simulate_press("right")
        step(w, inp)
        inp.simulate_press("jump")
        step(w, inp)
        self.assertGreater(p.rect.x, x)
        self.assertLess(p.vy, 0)
        self.assertTrue(p.try_dash())

    def test_wall_ignores_invulnerability(self):
        w = make_world(enemies=False)
        inp = InputState()
        settle(w, inp)
        w.player.take_damage(1)
        w.wall.segments[0].front_x = w.player.rect.left + 1
        step(w, inp)
        self.assertEqual(w.state, DEAD)
        self.assertEqual(w.death_cause, "wall")


if __name__ == "__main__":
    unittest.main()
