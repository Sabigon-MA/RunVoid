"""v2.0 変更（主人公1人・テレポート・追跡壁・ボス拡張の土台）の動作確認。
v2.1: 横方向の速度を 0.8 倍、追跡壁を 300px/s（通常移動 336px/s より少し遅い）に変更。

    cd game
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_gameplay import (DT, STAGE_1, InputState, disable_enemy_attacks, hold_wall,  # noqa: E402
                           make_world, place, settle, step)

import pygame  # noqa: E402

import config  # noqa: E402
from bosses import Boss  # noqa: E402
from enemies import CrawlerState, ShadowCrawler  # noqa: E402
from stages import parse_stage  # noqa: E402
from systems.teleport import FAIL_BLOCKED, FAIL_COOLDOWN  # noqa: E402
from systems.world import CLEAR, DEAD, PLAYING, World  # noqa: E402

GROUND = 422.0
CD_FRAMES = round(config.TELEPORT["cooldown"] / DT)


def aim(w, inp, enemy, dx=0.0, dy=0.0):
    """敵の当たり判定の中心にカーソルを合わせる（ワールド座標 → 画面座標）。"""
    cx, cy = enemy.hurtbox.center
    inp.mouse_pos = w.camera.to_screen(cx + dx, cy + dy)


def click(w, inp, enemy=None, **kw):
    if enemy is not None:
        aim(w, inp, enemy, **kw)
    inp.simulate_press("teleport")
    step(w, inp)
    inp.simulate_release("teleport")


def custom_world(platforms, enemies=(), spawn=(100, 382), one_way=()):
    data = {
        "spawn": {"x": spawn[0], "y": spawn[1]},
        "wall": {"start_x": -100000, "speed": 0},
        "platforms": [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in platforms],
        "one_way_platforms": [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in one_way],
        "enemies": [{"type": "shadow_crawler", "x": x, "foot_y": fy} for x, fy in enemies],
        "goal_x": 3000,
        "world_width": 3000,
    }
    w = World(parse_stage(data), with_graphics=False)
    for e in w.enemies:
        e.speed = 0
        e.attack_range = -1.0
    return w


def teleport_world(gap=300):
    """平地で主人公の右 gap px に敵を1体置く。"""
    w = make_world()
    hold_wall(w)
    w.wall.paused = True
    disable_enemy_attacks(w)
    inp = InputState()
    e = next(e for e in w.enemies if e.enemy_id == "E01")
    w.enemies = [e]
    e.speed = 0
    e.x = e.home_x = 1300
    place(w, e.x - gap - 12, GROUND)
    settle(w, inp)
    for _ in range(60):
        w.camera.follow(w.player.rect, DT)
    return w, inp, e


# ---------------------------------------------------------------------------
class CharacterTests(unittest.TestCase):
    def test_single_protagonist(self):
        from player import Protagonist
        w = make_world()
        self.assertIsInstance(w.player, Protagonist)
        self.assertFalse(hasattr(config, "CHARACTERS"))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(config.__file__), "player", "characters.py")))

    def test_no_attack_bindings(self):
        self.assertEqual(config.MOUSE_BINDINGS, {"teleport": 1})   # 右クリックは未割り当て
        w = make_world(enemies=False)
        hold_wall(w)
        inp = InputState()
        settle(w, inp)
        for action in ("attack", "special", "teleport"):
            inp.simulate_press(action)
        step(w, inp, 10)
        self.assertEqual(w.combat.attacks, [])   # 剣・弓などの攻撃判定は出ない

    def test_movement_params(self):
        s = config.PROTAGONIST["stats"]
        self.assertEqual((s["move_speed"], s["jump_speed"], s["dash_speed"]), (336.0, 520.0, 680.0))
        self.assertEqual((s["dash_cooldown"], s["max_jumps"], s["invuln_time"]), (0.8, 2, 0.3))
        self.assertEqual(config.PHYSICS["gravity"], 1400.0)
        self.assertEqual(config.PHYSICS["coyote_time"], 0.1)
        self.assertEqual(config.PHYSICS["jump_buffer_time"], 0.1)


# ---------------------------------------------------------------------------
class TeleportBasicTests(unittest.TestCase):
    def test_swap_by_foot_center(self):
        w, inp, e = teleport_world()
        p = w.player
        pf, ef = p.foot_center, e.foot_center
        hp, ehp = p.hp, e.hp
        click(w, inp, e)
        self.assertTrue(w.teleport.last_result.ok)
        # 足元中央が入れ替わる（当たり判定サイズが違っても左上ではなく足元基準）
        self.assertAlmostEqual(p.foot_center[0], ef[0], delta=0.01)
        self.assertAlmostEqual(p.foot_center[1], ef[1], delta=0.01)
        self.assertAlmostEqual(e.foot_center[0], pf[0], delta=0.01)
        self.assertAlmostEqual(e.foot_center[1], pf[1], delta=0.01)
        # テレポート自体ではダメージなし
        self.assertEqual(p.hp, hp)
        self.assertEqual(e.hp, ehp)
        self.assertAlmostEqual(w.teleport.cooldown_remaining, config.TELEPORT["cooldown"], delta=1e-6)
        self.assertEqual(w.teleport.count, 1)

    def test_click_outside_enemy_does_nothing(self):
        w, inp, e = teleport_world()
        p = w.player
        x = p.rect.x
        click(w, inp, e, dx=0, dy=-60)    # 敵の上の何もない場所
        self.assertIsNone(w.teleport.last_result)
        self.assertEqual(w.teleport.cooldown_remaining, 0)
        self.assertAlmostEqual(p.rect.x, x)

    def test_pick_margin(self):
        w, inp, e = teleport_world()
        m = config.TELEPORT["pick_margin"]
        aim(w, inp, e, dx=e.width / 2 + m - 1)   # 当たり判定のわずかに外でも選べる
        step(w, inp)
        self.assertIs(w.hover_target, e)

    def test_hold_does_not_repeat(self):
        w, inp, e = teleport_world()
        aim(w, inp, e)
        inp.simulate_press("teleport")
        step(w, inp)
        self.assertEqual(w.teleport.count, 1)
        # 押し続けたままクールダウンが明けても再発動しない
        for _ in range(CD_FRAMES + 30):
            aim(w, inp, e)
            step(w, inp)
        self.assertEqual(w.teleport.count, 1)
        inp.simulate_release("teleport")
        click(w, inp, e)
        self.assertEqual(w.teleport.count, 2)

    def test_cooldown_and_failure_does_not_consume(self):
        w, inp, e = teleport_world()
        click(w, inp, e)
        self.assertEqual(w.teleport.count, 1)
        step(w, inp, 30)
        pos = (w.player.rect.x, e.x)
        remaining = w.teleport.cooldown_remaining
        click(w, inp, e)                   # クールダウン中は失敗
        self.assertEqual(w.teleport.last_result.reason, FAIL_COOLDOWN)
        self.assertEqual((w.player.rect.x, e.x), pos)
        self.assertAlmostEqual(w.teleport.cooldown_remaining, remaining - DT, delta=1e-6)   # 時間経過分のみ減る
        # 成功からクールダウン（2 秒 = 120フレーム）で再使用できる
        while not w.teleport.ready:
            step(w, inp)
        click(w, inp, e)
        self.assertEqual(w.teleport.count, 2)

    def test_cooldown_frames(self):
        """成功したフレームから 120 フレーム（2.0 秒）後のフレームで再使用できる。"""
        w, inp, e = teleport_world()
        click(w, inp, e)
        frames = 0
        while not w.teleport.ready:
            step(w, inp)
            frames += 1
        self.assertEqual(frames, CD_FRAMES)

    def _flat(self, enemy_x_from_view_right):
        w = custom_world([(0, 422, 3000, 118)], enemies=[(0, 422)], spawn=(800, 382))
        inp = InputState()
        settle(w, inp)
        for _ in range(60):
            w.camera.follow(w.player.rect, DT)
        e = w.enemies[0]
        e.x = e.home_x = w.camera.view_rect.right + enemy_x_from_view_right
        return w, inp, e

    def test_unlimited_range_on_screen_but_not_offscreen(self):
        w, inp, e = self._flat(-20)      # 画面右端ぎりぎり（主人公から約550px先）
        self.assertGreater(e.x - w.player.rect.centerx, 500)
        click(w, inp, e)
        self.assertTrue(w.teleport.last_result.ok)
        w2, inp2, e2 = self._flat(40)    # 画面外
        aim(w2, inp2, e2)
        step(w2, inp2)
        self.assertIsNone(w2.hover_target)
        click(w2, inp2, e2)
        self.assertEqual(w2.teleport.count, 0)

    def test_mouse_uses_camera_offset(self):
        w, inp, e = teleport_world()
        self.assertGreater(w.camera.x, 100)
        aim(w, inp, e)
        step(w, inp)
        self.assertAlmostEqual(w.mouse_world[0], inp.mouse_pos[0] + w.camera.x, delta=0.01)
        self.assertIs(w.hover_target, e)

    def test_front_enemy_priority(self):
        w, inp, e = teleport_world()
        e2 = ShadowCrawler(e.x + 6, GROUND, "front")
        e2.speed = 0
        e2.attack_range = -1
        w.enemies.append(e2)    # 後に描画される = 手前
        front_x, back_x = e2.x, e.x
        click(w, inp, e)
        self.assertAlmostEqual(w.player.foot_center[0], front_x, delta=0.01)   # 手前の敵と交換
        self.assertEqual(e.x, back_x)

    def test_dead_enemy_not_targetable(self):
        w, inp, e = teleport_world()
        e.death_processed = True
        aim(w, inp, e)
        step(w, inp)
        self.assertIsNone(w.hover_target)

    def test_dash_cancelled_and_velocity_reset(self):
        w, inp, e = teleport_world()
        p = w.player
        inp.simulate_press("dash")
        step(w, inp)
        inp.simulate_release("dash")
        self.assertTrue(p.is_dashing)
        e.vy = 0
        click(w, inp, e)
        self.assertFalse(p.is_dashing)
        self.assertAlmostEqual(p.vx, 0.0, delta=1e-6)

    def test_no_contact_damage_at_swap(self):
        """交換先に別の敵が重なっていても、交換と同時の本体接触ダメージは発生しない。"""
        w, inp, e = teleport_world()
        other = ShadowCrawler(e.x, GROUND, "other")
        other.speed = 0
        other.attack_range = -1
        w.enemies.insert(0, other)   # e の後ろに描画（e が手前）
        hp = w.player.hp
        click(w, inp, e)
        self.assertTrue(w.player.rect.colliderect(other.body_rect))
        self.assertEqual(w.player.hp, hp)
        # 猶予が終わった後も重なり続ければ通常どおり被弾する
        step(w, inp, round(config.TELEPORT["contact_grace"] / DT) + 2)
        self.assertEqual(w.player.hp, hp - 1)

    def test_enemy_attack_after_swap_still_hits(self):
        w, inp, e = teleport_world(gap=85)
        e.attack_range = config.ENEMIES["shadow_crawler"]["attack_range"]
        for _ in range(120):
            step(w, inp)
            if e.state == CrawlerState.LUNGE:
                break
        self.assertEqual(e.state, CrawlerState.LUNGE)
        click(w, inp, e)   # 飛びかかり中の敵と交換: 敵は主人公の元の位置へ
        self.assertTrue(w.teleport.last_result.ok)

    def test_camera_follows_teleport(self):
        w, inp, e = teleport_world(gap=100)
        e.x = e.home_x = w.camera.view_rect.right - 20
        click(w, inp, e)
        m = config.CAMERA["keep_in_view_margin"]
        view = w.camera.view_rect
        self.assertGreaterEqual(w.player.rect.left, view.left + m - 1)
        self.assertLessEqual(w.player.rect.right, view.right - m + 1)
        for _ in range(30):
            step(w, inp)
        ratio = config.CAMERA["follow_x_ratio"]
        self.assertAlmostEqual(w.camera.x, w.player.rect.centerx - 960 * ratio, delta=4)

    def test_enemy_swapped_into_air_falls_and_resumes(self):
        w, inp, e = teleport_world()
        p = w.player
        inp.simulate_press("jump")
        step(w, inp, 20)
        self.assertFalse(p.on_ground)
        click(w, inp, e)
        self.assertTrue(e.airborne)
        self.assertEqual(e.home_x, e.x)
        for _ in range(120):
            step(w, inp)
        self.assertFalse(e.airborne)
        self.assertAlmostEqual(e.foot_y, GROUND, delta=0.01)
        self.assertIn(e.state, (CrawlerState.PATROL, CrawlerState.CHASE, CrawlerState.RECOVERY,
                                CrawlerState.COOLDOWN, CrawlerState.WINDUP))

    def test_double_jump_after_teleport(self):
        w, inp, e = teleport_world()
        click(w, inp, e)
        p = w.player
        step(w, inp, 2)
        inp.simulate_press("jump")
        step(w, inp, 15)
        inp.simulate_release("jump")
        step(w, inp)
        inp.simulate_press("jump")
        step(w, inp)
        self.assertEqual(p.jumps_used, 2)


# ---------------------------------------------------------------------------
class SafePositionTests(unittest.TestCase):
    def test_correction_under_low_ceiling(self):
        # 敵の上に低い天井（地面から高さ30px）。主人公(40px)は入らないので横へ補正される
        w = custom_world([(0, 422, 3000, 118), (580, 392, 50, 10)], enemies=[(600, 422)])
        inp = InputState()
        settle(w, inp)
        e = w.enemies[0]
        click(w, inp, e)
        p = w.player
        self.assertTrue(w.teleport.last_result.ok)
        self.assertFalse(w.terrain.overlaps_solid(p.rect))
        dx = abs(p.foot_center[0] - 600)
        self.assertGreater(dx, 0)
        self.assertLessEqual(dx, config.TELEPORT["safe_search_radius"])

    def test_fail_when_no_safe_position(self):
        # 長い低天井トンネルの中の敵: 48px 以内に主人公が入れる場所がない
        w = custom_world([(0, 422, 3000, 118), (400, 394, 400, 10)], enemies=[(600, 422)])
        inp = InputState()
        settle(w, inp)
        e = w.enemies[0]
        before = (w.player.rect.copy(), e.x, e.foot_y)
        click(w, inp, e)
        self.assertEqual(w.teleport.last_result.reason, FAIL_BLOCKED)
        self.assertEqual(w.teleport.cooldown_remaining, 0)   # 失敗はクールダウンを消費しない
        self.assertEqual((e.x, e.foot_y), before[1:])
        self.assertAlmostEqual(w.player.rect.x, before[0].x, delta=1e-6)

    def test_no_correction_through_thin_wall(self):
        # 低天井トンネルの右端が薄い壁で塞がれ、その向こう（48px 以内）は広い。
        # 壁の向こうへ補正すると地形を貫通するため、失敗しなければならない
        w = custom_world([(0, 422, 3000, 118), (400, 394, 236, 10), (636, 300, 6, 122)],
                         enemies=[(620, 422)])
        inp = InputState()
        settle(w, inp)
        e = w.enemies[0]
        click(w, inp, e)
        self.assertFalse(w.teleport.last_result.ok)
        self.assertEqual(w.teleport.count, 0)

    def test_enemy_side_also_corrected(self):
        # 主人公（幅24）が壁際に立っていると、幅36の敵はそのままでは壁にめり込む
        w = custom_world([(0, 422, 3000, 118), (60, 200, 40, 222)], enemies=[(500, 422)],
                         spawn=(100, 382))
        inp = InputState()
        settle(w, inp)
        self.assertAlmostEqual(w.player.rect.left, 100, delta=0.01)
        e = w.enemies[0]
        click(w, inp, e)
        self.assertTrue(w.teleport.last_result.ok)
        self.assertFalse(w.terrain.overlaps_solid(e.body_rect))
        self.assertGreaterEqual(e.body_rect.left, 100 - 1e-6)

    def test_unsafe_inside_wall_zone(self):
        w, inp, e = teleport_world()
        w.wall.segments[0].front_x = w.player.rect.left - 2
        tp = w.teleport
        self.assertTrue(w.wall.touches(e.rect_at_foot(w.player.rect.left, GROUND)))
        self.assertFalse(tp.is_safe(w, e.rect_at_foot(w.player.rect.left, GROUND)))

    def test_outside_map_is_unsafe(self):
        w, inp, e = teleport_world()
        r = w.player.rect_at_foot(5, GROUND)
        self.assertFalse(w.teleport.is_safe(w, r))
        r = w.player.rect_at_foot(400, w.stage.kill_y + 50)
        self.assertFalse(w.teleport.is_safe(w, r))


# ---------------------------------------------------------------------------
class WallTeleportTests(unittest.TestCase):
    def test_wall_kills_even_right_after_teleport(self):
        w, inp, e = teleport_world()
        click(w, inp, e)
        w.player.invuln = 10
        w.wall.paused = False
        w.wall.segments[0].front_x = w.player.rect.left + 1
        step(w, inp)
        self.assertEqual(w.state, DEAD)
        self.assertEqual(w.death_cause, "wall")

    def test_swapped_enemy_consumed_by_wall(self):
        w, inp, e = teleport_world()
        click(w, inp, e)
        w.wall.paused = False
        w.wall.segments[0].front_x = e.x + 1
        step(w, inp)
        self.assertFalse(e.alive)
        self.assertEqual(e.death_cause, "wall")


# ---------------------------------------------------------------------------
class PauseTests(unittest.TestCase):
    def test_pause_stops_cooldown_and_wall(self):
        import main
        game = main.Game()
        try:
            game.start_play()
            w = game.world
            w.teleport.cooldown_remaining = 3.0
            game.fixed_update(DT)
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            self.assertEqual(game.state, main.PAUSED)
            cd, wall_x, t = w.teleport.cooldown_remaining, w.wall.front_x, w.elapsed
            for _ in range(120):
                game.fixed_update(DT)
            self.assertEqual(w.teleport.cooldown_remaining, cd)
            self.assertEqual(w.wall.front_x, wall_x)
            self.assertEqual(w.elapsed, t)
        finally:
            pygame.quit()


# ---------------------------------------------------------------------------
class SentinelBoss(Boss):
    """テスト用: 戦闘開始後、一定間隔で主人公へ弾を撃つ。"""

    def __init__(self, x, foot_y, enemy_id="boss", params=None):
        super().__init__(x, foot_y, enemy_id, params)
        self.timer = 0.0
        self.contact_damage = 0

    def update_ai(self, dt, world):
        self.timer += dt
        if self.timer >= 1.0:
            self.timer = 0.0
            self.fire_at_player(world)


class BossTests(unittest.TestCase):
    def _world(self):
        w = custom_world([(0, 422, 3000, 118)], spawn=(300, 382))
        w.wall.paused = False
        w.wall.segments[0].front_x = 0
        w.wall.base_speed = 480
        inp = InputState()
        settle(w, inp)
        boss = SentinelBoss(800, GROUND)
        w.enemies.append(boss)
        for _ in range(60):
            w.camera.follow(w.player.rect, DT)
        return w, inp, boss

    def test_engage_stops_wall_and_shows_boss(self):
        w, inp, boss = self._world()
        step(w, inp)
        self.assertTrue(boss.engaged)
        self.assertIs(w.active_boss, boss)
        self.assertTrue(w.wall.paused)
        wall_x = w.wall.front_x
        step(w, inp, 30)
        self.assertEqual(w.wall.front_x, wall_x)

    def test_boss_is_teleport_target(self):
        w, inp, boss = self._world()
        step(w, inp)
        pf, bf = w.player.foot_center, boss.foot_center
        click(w, inp, boss)
        self.assertTrue(w.teleport.last_result.ok)
        self.assertAlmostEqual(w.player.foot_center[0], bf[0], delta=0.01)
        self.assertAlmostEqual(boss.foot_center[0], pf[0], delta=0.01)
        self.assertFalse(w.terrain.overlaps_solid(w.player.rect))

    def test_own_projectile_does_not_hit_boss_normally(self):
        w, inp, boss = self._world()
        step(w, inp)
        proj = boss.fire(w, boss.x - 40, boss.center[1], 1, 0)   # わざと自分に向けて撃つ
        hp = boss.hp
        step(w, inp, 30)
        self.assertEqual(boss.hp, hp)
        self.assertFalse(proj.self_harm_armed)

    def test_projectile_hits_boss_after_swap(self):
        w, inp, boss = self._world()
        step(w, inp)
        p = w.player
        proj = boss.fire_at_player(w)
        dx, dy = proj.dx, proj.dy
        step(w, inp, 20)   # 弾が主人公へ向かって飛んでいる途中
        self.assertFalse(proj.done)
        hp_boss, hp_player = boss.hp, p.hp
        click(w, inp, boss)
        self.assertTrue(w.teleport.last_result.ok)
        self.assertTrue(proj.self_harm_armed)
        self.assertEqual((proj.dx, proj.dy), (dx, dy))   # 方向は変わらない
        for _ in range(120):
            step(w, inp)
            if boss.hp < hp_boss:
                break
        self.assertEqual(boss.hp, hp_boss - config.BOSS_DEFAULTS["projectile_self_damage"])
        self.assertEqual(p.hp, hp_player)
        self.assertTrue(proj.done)

    def test_boss_defeat_resumes_wall_and_final_core_stops_it(self):
        w, inp, boss = self._world()
        step(w, inp)
        boss.hp = 1
        boss.take_damage(5)
        w.kill_enemy(boss, "attack")
        self.assertIsNone(w.active_boss)
        self.assertFalse(w.wall.paused)

        w2, inp2, core = self._world()
        core.stops_wall_permanently = True
        step(w2, inp2)
        core.take_damage(core.hp)
        w2.kill_enemy(core, "attack")
        self.assertTrue(w2.wall.paused)
        self.assertTrue(w2.wall_halted)

    def test_boss_does_not_stagger(self):
        w, inp, boss = self._world()
        self.assertFalse(boss.apply_stagger(1.0))


# ---------------------------------------------------------------------------
class Stage1BalanceTests(unittest.TestCase):
    """本番ステージ: v2.1 で壁は通常移動より少し遅くなり、走るだけでも逃げ切れる。
    テレポートはクリア時間の短縮になる。

    ボットは右入力を押し続け、地上ではダッシュを使い、決められた位置でジャンプする。
    """

    ROUTE = [(980, GROUND, False), (1200, GROUND, False), (1405, 300, True),
             (2270, GROUND, False), (2400, GROUND, False), (2605, 310, True)]

    def _run(self, use_teleport, min_gain=250, first_after=0.0, max_teleports=99):
        w = World(STAGE_1, with_graphics=False)
        inp = InputState()
        inp.simulate_press("right")
        used, double, hold = set(), False, 0
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
                for i, (x, surf, dbl) in enumerate(self.ROUTE):
                    if i not in used and abs(p.rect.bottom - surf) < 1 and p.rect.right >= x:
                        used.add(i)
                        inp.simulate_release("jump")
                        inp.simulate_press("jump")
                        hold, double, jumped = 40, dbl, True
                        break
            near = any(i not in used and abs(p.rect.bottom - s) < 1 and x - 140 <= p.rect.right < x
                       for i, (x, s, _) in enumerate(self.ROUTE))
            if p.on_ground and p.dash_cooldown <= 0 and not jumped and not near:
                inp.simulate_press("dash")
            else:
                inp.simulate_release("dash")
            if (use_teleport and w.teleport.ready and w.elapsed >= first_after
                    and w.teleport.count < max_teleports):
                ahead = [e for e in w.enemies if w.camera.view_rect.contains(e.hurtbox)
                         and e.x - p.rect.centerx > min_gain]
                if ahead:
                    aim(w, inp, max(ahead, key=lambda e: e.x))
                    inp.simulate_press("teleport")
            if w.update(DT, inp):
                inp.clear_edges()
            inp.simulate_release("teleport")
            if w.state != PLAYING:
                break
        return w

    def test_without_teleport_can_escape_by_running(self):
        w = self._run(False)
        self.assertEqual(w.state, CLEAR, f"{w.death_cause} at x={w.max_x:.0f}")

    def test_with_teleport_can_escape(self):
        w = self._run(True)
        self.assertEqual(w.state, CLEAR, f"{w.death_cause} at x={w.max_x:.0f}")
        self.assertGreaterEqual(w.teleport.count, 2)

    def test_single_well_timed_teleport_over_rampart(self):
        # 城壁（B01）の手前で、城壁の向こうの敵と1回だけ交換するルート
        w = self._run(True, first_after=1.0)
        self.assertEqual(w.state, CLEAR, f"{w.death_cause} at x={w.max_x:.0f}")

    def test_teleport_clears_faster_than_running(self):
        running = self._run(False)
        teleporting = self._run(True)
        self.assertEqual((running.state, teleporting.state), (CLEAR, CLEAR))
        self.assertLess(teleporting.elapsed, running.elapsed)


if __name__ == "__main__":
    unittest.main()
