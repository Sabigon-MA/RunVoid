"""v2.5 ステージ1のチェックポイント（案A: 区間3の穴を越えた所 x=1,560、追跡壁は 800px 後ろから）。

仕様:
    ・そのプレイ（タイトルから始めた一連の挑戦）で x=1,560 を越えてから死ぬと有効になる。
      初回は必ず最初から走る（壁に追われる流れと、前半の交換で時間を稼ぐ学びを残す）。
    ・有効になった後の死亡画面は「チェックポイントから」「最初から」「タイトルへ戻る」。
    ・チェックポイントからの開始で変わるのは出現位置と追跡壁の開始位置だけ。敵・タイマー・テレポートは最初の状態。
    ・タイトルへ戻る、「最初から」、クリア後の「もう一度プレイ」で解除。
    ・クリア時間・生存時間はチェックポイントからの時間で、画面に「（チェックポイントから）」と出す。
"""
import dataclasses
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from test_gameplay import DT, STAGE_1  # noqa: E402
import stage1_bot as bot  # noqa: E402
from stages.loader import CheckpointDef, StageFormatError, WallDef, parse_stage  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import World  # noqa: E402

CP = STAGE_1.checkpoint


def _raw(**checkpoint):
    import json
    from stages.loader import STAGE_DIR
    with open(STAGE_DIR / "stage_1.json", encoding="utf-8") as f:
        raw = json.load(f)
    if checkpoint:
        raw["checkpoint"] = checkpoint
    else:
        raw.pop("checkpoint")
    return raw


class LoaderTests(unittest.TestCase):
    def test_stage1_checkpoint(self):
        self.assertEqual(CP, CheckpointDef("CP1", 1560.0, 382.0, 800.0))
        spawn, wall = STAGE_1.start(from_checkpoint=True)
        self.assertEqual(spawn, (1560.0, 382.0))
        self.assertEqual(wall, WallDef(760.0, STAGE_1.wall.speed, STAGE_1.wall.thickness))
        self.assertEqual(STAGE_1.start(), (STAGE_1.spawn, STAGE_1.wall))

    def test_no_checkpoint_is_backward_compatible(self):
        st = parse_stage(_raw())
        self.assertIsNone(st.checkpoint)
        self.assertEqual(st.start(from_checkpoint=True), (st.spawn, st.wall))
        w = World(st, with_graphics=False, from_checkpoint=True)
        self.assertFalse(w.from_checkpoint)
        self.assertFalse(w.passed_checkpoint)

    def test_validation(self):
        for bad in (dict(x=-1, y=382, wall_gap=800), dict(x=3200, y=382, wall_gap=800),
                    dict(x=1560, y=382, wall_gap=0)):
            with self.assertRaises(StageFormatError):
                parse_stage(_raw(**bad))
        with self.assertRaises(StageFormatError):
            parse_stage(_raw(x=1560, y=382))          # wall_gap がない


class CheckpointWorldTests(unittest.TestCase):
    def test_only_spawn_and_wall_change(self):
        a = World(STAGE_1, with_graphics=False)
        b = World(STAGE_1, with_graphics=False, from_checkpoint=True)
        self.assertTrue(b.from_checkpoint)
        self.assertEqual(b.player.rect.x, CP.x)
        self.assertEqual(b.wall.front_x, CP.x - CP.wall_gap)
        self.assertEqual(b.player.rect.x - b.wall.front_x, CP.wall_gap)
        self.assertEqual([tuple(e.body_rect) for e in a.enemies], [tuple(e.body_rect) for e in b.enemies])
        self.assertEqual((b.elapsed, b.teleport.count, b.player.hp), (0.0, 0, a.player.hp))
        self.assertIs(b.stage, STAGE_1)
        self.assertFalse(a.passed_checkpoint)
        self.assertTrue(b.passed_checkpoint)

    def test_checkpoint_is_safe_ground(self):
        """着地点は区間4の地面（G03）の上。ゲート・穴・台座から離れていて、待っても2秒は安全。"""
        g03 = next(p for p in STAGE_1.platforms if p.id == "G03")
        self.assertTrue(g03.x + 40 <= CP.x and CP.x + 24 <= g03.x + g03.w)
        w = World(STAGE_1, with_graphics=False, from_checkpoint=True)
        inp = InputState()
        for _ in range(120):
            w.update(DT, inp); inp.clear_edges()
        self.assertEqual(w.state, "playing")
        self.assertTrue(w.player.on_ground)
        self.assertEqual(w.player.rect.bottom, g03.y)
        self.assertEqual(w.player.rect.x, CP.x)

    def test_matches_the_simulated_plan(self):
        """retry_compare.py の模擬（出現位置と壁だけを差し替えたステージ）と同じ挙動。"""
        sim = dataclasses.replace(STAGE_1, spawn=(CP.x, CP.y),
                                  wall=WallDef(CP.x - CP.wall_gap, STAGE_1.wall.speed, STAGE_1.wall.thickness))
        for kw in (dict(policy="none"), dict(policy="required", gate_delay=1.0, gate2_delay=0.5),
                   dict(policy="required", dash=False, gate_delay=2.0)):
            r1 = bot.play(STAGE_1, from_checkpoint=True, record=True, max_time=12, **kw)
            r2 = bot.play(sim, record=True, max_time=12, **kw)
            self.assertEqual(r1.rows, r2.rows, kw)


class CheckpointBalanceTests(unittest.TestCase):
    """チェックポイントからでもゲート1はテレポート必須。考えられる時間は通常（2.9秒／ダッシュ 3.55秒）を超えない。"""

    def test_gate_still_required(self):
        r = bot.play(STAGE_1, policy="none", from_checkpoint=True, max_time=20)
        self.assertEqual(r.state, "dead")
        self.assertLess(r.world.player.rect.right, 2320 + 1)

    def test_think_time(self):
        for dash, ok, ng in ((False, 2.65, 2.8), (True, 3.1, 3.25)):
            self.assertEqual(bot.play(STAGE_1, policy="required", dash=dash, gate_delay=ok, gate2_delay=0.0,
                                      from_checkpoint=True).state, "clear", (dash, ok))
            self.assertEqual(bot.play(STAGE_1, policy="required", dash=dash, gate_delay=ng, gate2_delay=0.0,
                                      from_checkpoint=True).state, "dead", (dash, ng))
            # 通常の開始で考えられる時間より長くはならない（緊張感を下げない）
            self.assertEqual(bot.play(STAGE_1, policy="required", dash=dash, gate_delay=ng + 0.35,
                                      gate2_delay=0.0).state, "dead")

    def test_reaches_gate_quickly(self):
        r = bot.play(STAGE_1, policy="none", dash=False, from_checkpoint=True, max_time=20)
        normal = bot.play(STAGE_1, policy="none", dash=False, max_time=20)
        self.assertLess(r.arrive["GATE1"][0], 2.5)
        self.assertGreater(normal.arrive["GATE1"][0], 6.0)


class GameFlowTests(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.game = main.Game()

    def _labels(self):
        return [(b.label, b.action) for b in self.game.overlay.menu.buttons]

    def _press(self, action):
        g = self.game
        for _ in range(45):                       # 死亡・クリア画面は 0.6 秒入力を受け付けない
            g.fixed_update(DT)
        btn = next(b for b in g.overlay.menu.buttons if b.action == action)
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))

    def _die(self, past_checkpoint):
        g = self.game
        if past_checkpoint:                      # 区間5の穴（2,900〜2,980）へ落とす
            g.world.player.rect.topleft = (2925, 300)
            g.world.player.vy = 0
        for _ in range(60 * 8):
            g.fixed_update(DT)
            if g.state == self.main.DEAD_SCREEN:
                return
        self.fail("死ななかった")

    def test_first_attempt_is_from_start(self):
        g = self.game
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertFalse(g.world.from_checkpoint)
        self.assertEqual(g.world.player.rect.x, STAGE_1.spawn[0])
        self._die(past_checkpoint=False)          # チェックポイントより前で死亡（壁）
        self.assertFalse(g.checkpoint_ready)
        self.assertEqual(self._labels(), [("リトライ", "retry"), ("タイトルへ戻る", "title")])
        self._press("retry")
        self.assertFalse(g.world.from_checkpoint)

    def test_unlocks_after_dying_past_checkpoint(self):
        g = self.game
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self._die(past_checkpoint=True)
        self.assertTrue(g.checkpoint_ready)
        self.assertEqual(self._labels(), [("チェックポイントから", "retry"), ("最初から", "restart"),
                                          ("タイトルへ戻る", "title")])
        g.draw()
        self._press("retry")
        self.assertEqual(g.state, self.main.PLAY)
        self.assertTrue(g.world.from_checkpoint)
        self.assertEqual(g.world.player.rect.x, CP.x)
        self.assertEqual(g.world.elapsed, 0.0)
        g.draw()                                  # HUD の「チェックポイントから再開」
        # ポーズのリトライもチェックポイントから
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertIn(("リトライ（チェックポイント）", "retry"), self._labels())
        g._resume()
        # チェックポイントから始めて死んでも有効のまま。「最初から」で解除
        self._die(past_checkpoint=False)
        self.assertIn("（チェックポイントから）", g.overlay.lines[2])
        self.assertTrue(g.checkpoint_ready)
        self._press("restart")
        self.assertFalse(g.checkpoint_ready)
        self.assertFalse(g.world.from_checkpoint)
        self.assertEqual(g.world.player.rect.x, STAGE_1.spawn[0])

    def test_title_and_clear_reset(self):
        g = self.game
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self._die(past_checkpoint=True)
        self._press("title")
        self.assertFalse(g.checkpoint_ready)
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertFalse(g.world.from_checkpoint)
        # クリア後の「もう一度プレイ」も最初から
        g.checkpoint_ready = True
        g.start_play()
        g.world.state = "clear"
        g.fixed_update(DT)
        self.assertEqual(g.state, self.main.CLEAR_SCREEN)
        self._press("retry")
        self.assertFalse(g.checkpoint_ready)
        self.assertFalse(g.world.from_checkpoint)


def _game_after(world):
    """World（ボットや手動操作で進めたもの）を Game に載せ、死亡・クリアの画面遷移を本物の経路で通す。"""
    import main
    g = main.Game()
    g.world, g.state = world, main.PLAY
    g.fixed_update(DT)
    return g


def _free_world(x, graphics=False):
    """壁を止めて遠ざけ、主人公を G03 の上 x に置いた World。"""
    w = World(STAGE_1, with_graphics=graphics)
    w.wall.paused = True
    w.wall.segments[0].front_x = -1e5
    w.player.rect.topleft = (x, 382)
    w.camera.snap_to(w.player.rect)
    return w


def _primitives(obj, skip=()):
    """数値・真偽・文字列の属性。uid は生成順の通し番号なので比べない。"""
    return {k: v for k, v in vars(obj).items()
            if k not in skip and k != "uid" and isinstance(v, (int, float, bool, str, type(None)))}


class CheckpointBoundaryTests(unittest.TestCase):
    """Task 1: 意図しない有効化・無効化がないこと。通過の判定は「主人公の左端 x ≥ 1,560」。"""

    def _cross(self, dash):
        w = _free_world(1530)
        inp = InputState()
        inp.simulate_press("right")
        if dash:
            inp.simulate_press("dash")
        xs = []
        for _ in range(60):
            before = w.player.rect.x
            w.update(DT, inp); inp.clear_edges()
            xs.append((before, w.player.rect.x, w.checkpoint_lit, w.passed_checkpoint))
            if dash:
                inp.simulate_release("dash")
            if w.player.rect.x > 1700:
                break
        crossing = [i for i, (b, a, _, _) in enumerate(xs) if b < CP.x <= a]
        self.assertEqual(len(crossing), 1)
        for i, (b, a, lit, passed) in enumerate(xs):
            self.assertEqual(passed, a >= CP.x, i)          # 越えた瞬間に有効、その前は無効
            self.assertEqual(lit, passed, i)
        k = crossing[0]
        return xs[k][1] - xs[k][0]

    def test_walk_and_dash(self):
        step_walk = self._cross(dash=False)
        step_dash = self._cross(dash=True)
        self.assertGreater(step_dash, step_walk * 1.5)    # ダッシュの速さで越えても取りこぼさない

    def test_teleport_over_checkpoint(self):
        w = _free_world(1530)
        inp = InputState()
        for _ in range(5):
            w.update(DT, inp); inp.clear_edges()
        e02 = next(e for e in w.enemies if e.x > 1900 and e.x < 2100)
        self.assertFalse(w.passed_checkpoint)
        bot.click(w, inp, e02)
        w.update(DT, inp); inp.clear_edges()
        self.assertEqual(w.teleport.count, 1)
        self.assertGreater(w.player.rect.x, 1900)            # 1,560 を一度も踏まずに越えた
        self.assertTrue(w.passed_checkpoint and w.checkpoint_lit)
        # そのまま壁に飲まれると、次のリトライはチェックポイントから
        w.wall.paused = False
        w.wall.segments[0].front_x = w.player.rect.left + 1
        g = _game_after(w)
        self.assertEqual(w.state, "dead")
        self.assertTrue(g.checkpoint_ready)

    def _die_at_crossing(self, offset):
        """越えるフレーム（offset=0）／その1フレーム前（offset=-1）に壁に飲まれる。"""
        ref = _free_world(1530); inp = InputState(); inp.simulate_press("right")
        lefts = []
        for _ in range(60):
            ref.update(DT, inp); inp.clear_edges(); lefts.append(ref.player.rect.left)
            if lefts[-1] >= CP.x:
                break
        k = len(lefts) - 1 + offset
        w = _free_world(1530); inp = InputState(); inp.simulate_press("right")
        for _ in range(k):
            w.update(DT, inp); inp.clear_edges()
        w.wall.paused = False
        w.wall.segments[0].front_x = lefts[k] - STAGE_1.wall.speed * DT + 0.5   # このフレームの壁の移動で追いつく
        w.update(DT, inp)
        self.assertEqual((w.state, w.death_cause), ("dead", "wall"))
        self.assertEqual(w.player.rect.left, lefts[k])
        return w

    def test_death_on_the_crossing_frame(self):
        w = self._die_at_crossing(0)
        self.assertGreaterEqual(w.player.rect.x, CP.x)
        self.assertTrue(_game_after(w).checkpoint_ready)
        w = self._die_at_crossing(-1)
        self.assertLess(w.player.rect.x, CP.x)
        g = _game_after(w)
        self.assertFalse(g.checkpoint_ready)
        self.assertEqual([b.action for b in g.overlay.menu.buttons], ["retry", "title"])

    def test_deaths_before_checkpoint_do_not_unlock(self):
        r = bot.play(STAGE_1, policy="none", dash=False, start_delay=3.0, max_time=10)   # 開始地点で壁に飲まれる
        self.assertEqual((r.state, r.world.death_cause), ("dead", "wall"))
        self.assertFalse(_game_after(r.world).checkpoint_ready)
        w = World(STAGE_1, with_graphics=False)                                     # 最初の穴に落ちる
        w.player.rect.topleft = (800, 440)
        for _ in range(120):
            w.update(DT, InputState())
            if w.state == "dead":
                break
        self.assertEqual(w.death_cause, "fall")
        self.assertFalse(_game_after(w).checkpoint_ready)

    def test_gate_deaths_unlock_and_keep(self):
        for kw in (dict(policy="none"), dict(policy="required", gate2_delay=6.0)):
            for cp in (False, True):
                r = bot.play(STAGE_1, from_checkpoint=cp, max_time=30, **kw)
                self.assertEqual((r.state, r.world.death_cause), ("dead", "wall"), (kw, cp))
                gate = 2320 if kw["policy"] == "none" else 3040
                self.assertLessEqual(r.world.player.rect.right, gate + 1)
                g = _game_after(r.world)
                self.assertTrue(g.checkpoint_ready, (kw, cp))
                self.assertEqual(g.overlay.menu.buttons[0].label, "チェックポイントから")

    def test_resume_then_immediate_death_keeps_checkpoint(self):
        import main
        g = main.Game()
        g.checkpoint_ready = True
        g.start_play()
        g.world.wall.segments[0].front_x = g.world.player.rect.left + 1
        g.fixed_update(DT)
        self.assertEqual(g.state, main.DEAD_SCREEN)
        self.assertLess(g.world.elapsed, 0.05)
        self.assertTrue(g.checkpoint_ready)
        for _ in range(45):
            g.fixed_update(DT)
        btn = g.overlay.menu.buttons[0]
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
        self.assertTrue(g.world.from_checkpoint)

    def test_restart_and_replay_do_not_leave_stale_checkpoint(self):
        import main
        # チェックポイントからクリア → クリア画面 → もう一度プレイ → 最初から、壁で死んでも無効のまま
        r = bot.play(STAGE_1, policy="required", gate2_delay=0.0, from_checkpoint=True)
        self.assertEqual(r.state, "clear")
        g = main.Game()
        g.checkpoint_ready = True
        g.world, g.state = r.world, main.PLAY
        g.fixed_update(DT)
        self.assertEqual(g.state, main.CLEAR_SCREEN)
        self.assertIn("（チェックポイントから）", g.overlay.lines[0])
        for _ in range(45):
            g.fixed_update(DT)
        btn = next(b for b in g.overlay.menu.buttons if b.action == "retry")
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
        self.assertFalse(g.checkpoint_ready)
        self.assertFalse(g.world.from_checkpoint)
        self.assertFalse(g.world.checkpoint_lit)
        for _ in range(60 * 4):
            g.fixed_update(DT)
        self.assertEqual(g.state, main.DEAD_SCREEN)
        self.assertFalse(g.checkpoint_ready)
        # ポーズのリトライも、無効なら最初から
        g.start_play()
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertIn(("リトライ", "retry"), [(b.label, b.action) for b in g.overlay.menu.buttons])


class CheckpointResumeConsistencyTests(unittest.TestCase):
    """Task 2: 再開時に通常開始と違うのは「出現位置・追跡壁の位置・カメラ位置・目印が起動済み」だけ。"""

    def setUp(self):
        self.n = World(STAGE_1)
        self.c = World(STAGE_1, from_checkpoint=True)

    def test_player_state(self):
        n, c = self.n.player, self.c.player
        self.assertEqual((c.rect.x, c.rect.bottom), (CP.x, 422.0))
        self.assertEqual((c.rect.w, c.rect.h), (n.rect.w, n.rect.h))
        self.assertEqual(_primitives(c), _primitives(n))       # HP・速度・ジャンプ・ダッシュ・空中ダッシュ・向きなど
        self.assertEqual((c.jumps_used, c.air_dashes_remaining, c.dash_cooldown), (0, c.max_air_dashes, 0.0))

    def test_wall_teleport_timer(self):
        self.assertEqual(self.c.wall_distance, CP.wall_gap)
        self.assertEqual(self.c.wall.front_x, CP.x - CP.wall_gap)
        self.assertEqual(_primitives(self.c.wall, skip=()), {**_primitives(self.n.wall)})
        self.assertEqual([_primitives(s, skip=("front_x",)) for s in self.c.wall.segments],
                         [_primitives(s, skip=("front_x",)) for s in self.n.wall.segments])
        self.assertEqual(_primitives(self.c.teleport), _primitives(self.n.teleport))
        self.assertTrue(self.c.teleport.ready)
        self.assertEqual((self.c.elapsed, self.c.teleport.count, self.c.hitstop_frames, self.c.contact_grace),
                         (0.0, 0, 0, 0.0))
        inp = InputState()
        for _ in range(60):
            self.c.update(DT, inp)
        self.assertAlmostEqual(self.c.wall_distance, CP.wall_gap - STAGE_1.wall.speed, places=3)
        self.assertAlmostEqual(self.c.elapsed, 1.0, places=6)

    def test_enemies(self):
        self.assertEqual(len(self.c.enemies), len(STAGE_1.enemies))
        for a, b in zip(self.n.enemies, self.c.enemies):
            self.assertEqual(tuple(a.body_rect), tuple(b.body_rect))
            self.assertEqual(_primitives(a), _primitives(b))

    def test_camera(self):
        ref = World(STAGE_1)
        ref.player.rect.topleft = (CP.x, CP.y)
        ref.camera.snap_to(ref.player.rect)
        self.assertEqual((self.c.camera.x, self.c.camera.y), (ref.camera.x, ref.camera.y))
        view = self.c.camera.view_rect
        self.assertTrue(view.contains(self.c.player.rect))
        self.assertFalse(self.c.wall_on_screen)                  # 壁は画面外（HUD の左端に距離を表示）
        cpm = self.c.terrain_renderer.checkpoint
        self.assertTrue(view.contains(pygame.Rect(*cpm.origin, cpm.W, cpm.H)))

    def test_background_and_terrain_draw_identically(self):
        """同じカメラ位置なら、背景と地形の描画は通常開始と画素単位で同じ（目印を起動済みに揃えた場合）。"""
        self.n.camera.x = self.c.camera.x
        self.n.terrain_renderer.set_checkpoint_lit(flash=False)
        for draw in (lambda w, s: w.background.draw(s, w.camera.x),
                     lambda w, s: w.terrain_renderer.draw(s, w.camera)):
            a, b = pygame.Surface((960, 540)), pygame.Surface((960, 540))
            draw(self.n, a); draw(self.c, b)
            self.assertEqual(pygame.image.tobytes(a, "RGB"), pygame.image.tobytes(b, "RGB"))


class CheckpointMarkerTests(unittest.TestCase):
    """Task 4: 目印は描画のみ。未起動と起動済みを見分けられる。"""

    def test_no_collision(self):
        plain = parse_stage(_raw())
        a, b = World(plain, with_graphics=False), World(STAGE_1, with_graphics=False)
        self.assertEqual([tuple(r) for r in a.terrain.solids], [tuple(r) for r in b.terrain.solids])
        # 同じ入力で x=1,560 をまたいで走ると、目印の有無で軌跡が完全に同じ
        trails = []
        for st in (plain, STAGE_1):
            w = World(st, with_graphics=True)
            w.wall.paused = True; w.wall.segments[0].front_x = -1e5
            w.player.rect.topleft = (1530, 382); w.camera.snap_to(w.player.rect)
            inp = InputState(); inp.simulate_press("right")
            trail = []
            for i in range(50):
                if i == 3:
                    inp.simulate_press("jump")
                w.update(DT, inp); inp.clear_edges()
                trail.append(tuple(w.player.rect))
            trails.append(trail)
        self.assertEqual(trails[0], trails[1])
        # 目印の上をクリックしても交換相手にはならない
        from systems.targeting import find_target
        w = World(STAGE_1)
        w.player.rect.x = 1450; w.camera.snap_to(w.player.rect)
        cpm = w.terrain_renderer.checkpoint
        self.assertIsNone(find_target(w.enemies, w.camera, (CP.x, cpm.origin[1] + cpm.core[1])))

    def test_position_does_not_hide_terrain(self):
        cpm = World(STAGE_1).terrain_renderer.checkpoint
        box = pygame.Rect(*cpm.origin, cpm.W, cpm.H)
        g03 = next(p for p in STAGE_1.platforms if p.id == "G03")
        self.assertEqual(box.bottom, g03.y + 2)                  # G03 の上に立つ
        self.assertGreaterEqual(box.left, g03.x + 8)             # 穴 1,300〜1,520 の縁から離れている
        for p in STAGE_1.platforms:
            if p.id != "G03":
                self.assertFalse(box.colliderect(p.to_rect()), p.id)
        for e in STAGE_1.enemies:
            self.assertGreater(abs(e.x - CP.x), 200)

    def _crop(self, w):
        s = pygame.Surface((960, 540)); w.draw(s)
        cpm = w.terrain_renderer.checkpoint
        return s.subsurface((cpm.origin[0] - w.camera.x, cpm.origin[1], cpm.W, cpm.H)).copy()

    @staticmethod
    def _violet(surf):
        n = 0
        for x in range(surf.get_width()):
            for y in range(surf.get_height()):
                r, g, b, _ = surf.get_at((x, y))
                n += b >= 200 and b > r + 40 and b > g + 40
        return n

    def test_unlit_and_lit_are_distinct(self):
        w = _free_world(1300, graphics=True)
        self.assertFalse(w.checkpoint_lit)
        unlit = self._crop(w)
        w.terrain_renderer.set_checkpoint_lit(flash=False)
        lit = self._crop(w)
        self.assertEqual(self._violet(unlit), 0)                 # 未起動は光らない
        self.assertGreater(self._violet(lit), 20)                # 起動済みは淡い青紫の光

    def test_activation_flash_and_resume_state(self):
        w = _free_world(1550, graphics=True)
        inp = InputState(); inp.simulate_press("right")
        while not w.checkpoint_lit:
            w.update(DT, inp); inp.clear_edges()
        self.assertLess(w.terrain_renderer.checkpoint_age, 0.05)     # 起動した瞬間に演出が始まる
        for _ in range(60):
            w.update(DT, inp)
        self.assertGreater(w.terrain_renderer.checkpoint_age, 0.9)   # 演出は 0.9 秒で終わる
        r = World(STAGE_1, from_checkpoint=True)
        self.assertTrue(r.checkpoint_lit and r.terrain_renderer.checkpoint_lit)
        self.assertGreater(r.terrain_renderer.checkpoint_age, 100)   # 再開時は演出なしで起動済み
        self.assertTrue(World(STAGE_1, with_graphics=False, from_checkpoint=True).checkpoint_lit)

    def test_drawing_does_not_touch_global_random(self):
        import random
        w = World(STAGE_1, from_checkpoint=True)
        state = random.getstate()
        s = pygame.Surface((960, 540))
        for _ in range(30):
            w.terrain_renderer.update(DT)
            w.terrain_renderer.draw(s, w.camera)
        self.assertEqual(random.getstate(), state)


if __name__ == "__main__":
    unittest.main()
