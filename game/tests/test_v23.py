"""v2.3: 実機QA反映（フォント先読み・表示モード・視認性・テレポート時カメラ）の回帰テスト。

物理トレース:
    tests/fixtures/physics_trace_v22.json は v2.2（表示改善前）のコードで記録した、ステージ1の
    自動プレイ3通りの毎ステップの状態。v2.3 の変更はすべて見た目・表示だけなので完全一致すること。
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
        rows.append([round(v, 4) for v in (p.rect.x, p.rect.y, p.vx, p.vy, w.wall.front_x)]
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


if __name__ == "__main__":
    unittest.main()
