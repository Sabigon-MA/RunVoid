"""ゲームロジックの動作確認テスト。

    cd game
    python -m unittest discover -s tests -v

画面を開かずに（SDL dummy ドライバ）World を直接動かして確認する。

v2.0: 地形に依存する移動・敵AIのテストは、v1.x のマップを保存したフィクスチャ
（tests/fixtures/legacy_stage.json、壁速度のみ 480 に更新）で行う。
本番ステージ（stages/stage_1.json）の検証は test_v20.py にある。
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import config  # noqa: E402
from enemies import CrawlerState  # noqa: E402
from stages import load_stage  # noqa: E402
from stages.loader import EnemyDef  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import CLEAR, DEAD, PLAYING, World  # noqa: E402

DT = config.FIXED_DT
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
STAGE = load_stage(os.path.join(FIXTURES, "legacy_stage.json"))
STAGE_1 = load_stage()


def make_world(enemies=True, stage=None) -> World:
    w = World(stage or STAGE, with_graphics=False)
    if not enemies:
        w.enemies = []
    return w


def step(world, inp, n=1):
    for _ in range(n):
        if world.update(DT, inp):   # ヒットストップ中は入力エッジを保持（main.Game と同じ）
            inp.clear_edges()
        if world.state != PLAYING:
            break


def disable_enemy_attacks(world):
    """接触ダメージや攻撃判定だけを確認したいテスト用に、敵の飛びかかりを止める。"""
    for e in world.enemies:
        e.attack_range = -1.0


def settle(world, inp):
    """スポーン直後の落下を終わらせる。"""
    step(world, inp, 10)


def hold_wall(world, x=-100000.0):
    """テスト中に壁が邪魔をしないよう後方へ下げる。"""
    world.wall.segments[0].front_x = x


def place(world, x, bottom):
    world.player.rect.x = x
    world.player.rect.bottom = bottom
    world.player.vx = world.player.vy = 0


class StageTests(unittest.TestCase):
    def test_stage_json_loaded(self):
        self.assertEqual(STAGE.name, "黄昏の廃王国")
        self.assertEqual(len(STAGE.platforms), 5)
        self.assertEqual(len(STAGE.one_way_platforms), 2)
        self.assertEqual(len(STAGE.enemies), 3)
        self.assertEqual(STAGE.spawn, (480.0, 382.0))
        self.assertEqual(STAGE.goal_x, 3200.0)
        self.assertEqual(STAGE.wall.speed, 480.0)

    def test_stage_1_loaded(self):
        self.assertEqual(STAGE_1.name, "黄昏の廃王国")
        self.assertEqual(STAGE_1.goal_x, 3200.0)
        self.assertEqual(STAGE_1.wall.speed, 300.0)
        self.assertGreaterEqual(len(STAGE_1.enemies), 3)


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.w = make_world(enemies=False)
        self.inp = InputState()
        hold_wall(self.w)

    def test_spawn_on_ground(self):
        settle(self.w, self.inp)
        self.assertTrue(self.w.player.on_ground)
        self.assertAlmostEqual(self.w.player.rect.bottom, 422.0, places=3)

    def test_walk_speed(self):
        settle(self.w, self.inp)
        self.inp.simulate_press("right")
        step(self.w, self.inp, 30)
        x0 = self.w.player.rect.x
        step(self.w, self.inp, 6)
        self.assertAlmostEqual((self.w.player.rect.x - x0) / (6 * DT), 336.0, delta=1.0)

    def _jump_height(self, hold_frames):
        settle(self.w, self.inp)
        start = self.w.player.rect.bottom
        self.inp.simulate_press("jump")
        best = start
        for i in range(90):
            if i == hold_frames:
                self.inp.simulate_release("jump")
            step(self.w, self.inp)
            best = min(best, self.w.player.rect.bottom)
        self.inp.simulate_release("jump")
        return start - best

    def test_variable_jump(self):
        full = self._jump_height(90)
        w2 = make_world(enemies=False)
        hold_wall(w2)
        self.w, self.inp = w2, InputState()
        tap = self._jump_height(3)
        # 一方通行足場 P02（地面から80px）に届き、短押しは明確に低い
        self.assertGreater(full, 96)
        self.assertLess(tap, full * 0.6)

    def test_coyote_time(self):
        place(self.w, 790, 422)   # G01 の右端（800）付近
        settle(self.w, self.inp)
        self.inp.simulate_press("right")
        while self.w.player.on_ground:
            step(self.w, self.inp)
        step(self.w, self.inp, 3)   # 崖から 3 フレーム後
        self.inp.simulate_press("jump")
        step(self.w, self.inp)
        self.assertLess(self.w.player.vy, 0)

    def test_dash_and_air_dash_once(self):
        settle(self.w, self.inp)
        x0 = self.w.player.rect.x
        self.inp.simulate_press("dash")
        step(self.w, self.inp, 9)
        self.assertGreater(self.w.player.rect.x - x0, 90)
        # 空中ダッシュは着地まで1回
        step(self.w, self.inp, 60)
        self.inp.simulate_press("jump")
        step(self.w, self.inp, 4)
        self.assertTrue(self.w.player.try_dash())
        self.w.player.dash_timer = 0
        self.w.player.dash_cooldown = 0
        self.assertFalse(self.w.player.try_dash())

    def test_dash_does_not_tunnel(self):
        place(self.w, 1380, 422)   # G03(1440, y=390) の段差手前
        settle(self.w, self.inp)
        self.inp.simulate_press("dash")
        step(self.w, self.inp, 12)
        self.assertLessEqual(self.w.player.rect.right, 1440.0 + 1e-6)

    def test_one_way_land_drop_and_pass_from_below(self):
        p = self.w.player
        # 下から通過して上に着地（P01: x=1200, y=326）
        place(self.w, 1260, 422)
        settle(self.w, self.inp)
        self.inp.simulate_press("jump")
        for _ in range(80):
            step(self.w, self.inp)
        self.inp.simulate_release("jump")
        self.assertTrue(p.on_ground and p.on_one_way)
        self.assertAlmostEqual(p.rect.bottom, 326.0, places=3)
        # S + Space で降下
        self.inp.simulate_press("down")
        self.inp.simulate_press("jump")
        step(self.w, self.inp, 60)
        self.inp.simulate_release("down")
        self.inp.simulate_release("jump")
        self.assertAlmostEqual(p.rect.bottom, 422.0, places=3)

    def test_fall_into_pit_kills(self):
        place(self.w, 830, 300)
        step(self.w, self.inp, 120)
        self.assertEqual(self.w.state, DEAD)
        self.assertEqual(self.w.death_cause, "fall")

    def test_goal_clear(self):
        place(self.w, 3150, 422)
        self.inp.simulate_press("right")
        step(self.w, self.inp, 60)
        self.assertEqual(self.w.state, CLEAR)

    def test_camera_follows_and_clamps(self):
        settle(self.w, self.inp)
        self.assertGreaterEqual(self.w.camera.x, 0)
        place(self.w, 2000, 422)
        step(self.w, self.inp, 120)
        ratio = config.CAMERA["follow_x_ratio"]
        self.assertAlmostEqual(self.w.camera.x, self.w.player.rect.centerx - 960 * ratio, delta=2)
        place(self.w, 3100, 422)
        step(self.w, self.inp, 120)
        self.assertAlmostEqual(self.w.camera.x, 3200 - 960, delta=0.5)


class WallTests(unittest.TestCase):
    def test_wall_speed(self):
        w = make_world(enemies=False)
        inp = InputState()
        step(w, inp, 60)
        self.assertAlmostEqual(w.wall.front_x, 480.0, delta=1e-6)

    def test_idle_player_is_caught(self):
        w = make_world(enemies=False)
        inp = InputState()
        step(w, inp, 200)
        self.assertEqual(w.state, DEAD)
        self.assertEqual(w.death_cause, "wall")
        # 480px / 480px/s = 1秒
        self.assertAlmostEqual(w.elapsed, 480 / 480, delta=0.05)

    def test_wall_slightly_slower_than_walking(self):
        # v2.1: 壁は主人公の通常移動より少し遅い（約9割）
        stats = config.PROTAGONIST["stats"]
        self.assertLess(STAGE_1.wall.speed, stats["move_speed"])
        self.assertGreaterEqual(STAGE_1.wall.speed, stats["move_speed"] * 0.85)

    def test_wall_ignores_invulnerability(self):
        w = make_world(enemies=False)
        inp = InputState()
        settle(w, inp)
        w.player.invuln = 10.0
        w.wall.segments[0].front_x = w.player.rect.left + 1
        step(w, inp)
        self.assertEqual(w.state, DEAD)
        self.assertEqual(w.death_cause, "wall")

    def test_enemy_consumed_by_wall(self):
        w = make_world()
        inp = InputState()
        e = w.enemies[0]
        w.wall.segments[0].front_x = e.x
        w.wall.paused = True
        place(w, 2000, 422)
        step(w, inp)
        self.assertNotIn(e, w.enemies)
        self.assertEqual(e.death_cause, "wall")


class EnemyTests(unittest.TestCase):
    def test_patrol_stays_on_platform(self):
        w = make_world()
        hold_wall(w)
        w.wall.paused = True
        inp = InputState()
        place(w, 3150, 422)   # 遠くに置く
        w.player.rect.y = -5000
        w.player.vy = 0
        # 落下死を避けるため update を直接回す
        bounds = {"E01": (896, 1440), "E02": (1440, 1824), "E03": (2560, 3200)}
        for _ in range(60 * 20):
            for e in w.enemies:
                e.update(DT, w)
                lo, hi = bounds[e.enemy_id]
                self.assertGreaterEqual(e.x - e.width / 2, lo - 1e-6)
                self.assertLessEqual(e.x + e.width / 2, hi + 1e-6)

    def test_chase_stops_at_cliff(self):
        w = make_world()
        hold_wall(w)
        e = next(e for e in w.enemies if e.enemy_id == "E02")   # G03 上
        place(w, 1860, 600)   # G03 右端の先（穴の上空扱い）
        w.player.rect.bottom = 400
        for _ in range(60 * 10):
            e.update(DT, w)
            # 追跡中も飛びかかり中も崖の外へ出ない
            self.assertLessEqual(e.x + e.width / 2, 1824 + 0.1)
        self.assertNotEqual(e.state, CrawlerState.PATROL)

    def test_detects_player(self):
        w = make_world()
        e = w.enemies[0]
        place(w, e.x + 200, 422)
        e.update(DT, w)
        self.assertEqual(e.state, CrawlerState.CHASE)
        place(w, e.x + 400, 422)
        e.update(DT, w)
        self.assertEqual(e.state, CrawlerState.PATROL)


class ContactTests(unittest.TestCase):
    def _overlap(self):
        w = make_world()
        hold_wall(w)
        disable_enemy_attacks(w)
        inp = InputState()
        e = w.enemies[0]
        e.speed = 0
        place(w, e.x - 12, 422)
        step(w, inp)
        return w

    def test_contact_damage_and_invulnerability(self):
        w = self._overlap()
        p = w.player
        self.assertEqual(p.hp, p.stats["max_hp"] - 1)
        self.assertGreater(p.invuln, 0)
        frames = round(p.stats["invuln_time"] / DT)   # v1.2: 0.3秒 = 18フレーム
        step(w, InputState(), frames - 1)   # 無敵中は追加ダメージなし
        self.assertEqual(p.hp, p.stats["max_hp"] - 1)
        step(w, InputState(), 1)            # 無敵終了と同時に再度被弾
        self.assertEqual(p.hp, p.stats["max_hp"] - 2)
        self.assertEqual(len(w.enemies), 3)   # 敵は接触でダメージを受けない
        self.assertEqual(w.enemies[0].hp, w.enemies[0].max_hp)

    def test_player_and_enemy_pass_through(self):
        w = make_world()
        hold_wall(w)
        disable_enemy_attacks(w)
        inp = InputState()
        e = w.enemies[0]
        e.speed = 0
        place(w, e.x - 80, 422)
        inp.simulate_press("right")
        step(w, inp, 40)
        self.assertGreater(w.player.rect.left, e.x + e.width / 2)


class GameSmokeTests(unittest.TestCase):
    """画面遷移と描画が例外なく動くか。"""

    def test_screens(self):
        import main
        game = main.Game()
        try:
            for _ in range(3):
                game.fixed_update(DT)
                game.draw()
            # タイトルの「ゲーム開始」で直接プレイ開始（キャラクター選択なし）
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(game.state, main.PLAY)
            self.assertFalse(hasattr(main, "SELECT"))
            game.input.simulate_press("right")
            for _ in range(20):
                game.fixed_update(DT)
            game.draw()
            game.input.simulate_release("right")
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            self.assertEqual(game.state, main.PAUSED)
            game.draw()
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            self.assertEqual(game.state, main.PLAY)
            for _ in range(60 * 6):
                game.fixed_update(DT)
            self.assertEqual(game.state, main.DEAD_SCREEN)
            game.draw()
            old_world = game.world
            game.start_play()   # リトライ
            self.assertIsNot(game.world, old_world)
            self.assertEqual(game.world.elapsed, 0)
            self.assertEqual(game.world.wall.front_x, STAGE_1.wall.start_x)
            self.assertEqual(len(game.world.enemies), len(STAGE_1.enemies))
            self.assertEqual(game.world.player.rect.topleft, (480, 382))
            self.assertEqual(game.world.teleport.cooldown_remaining, 0)
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
