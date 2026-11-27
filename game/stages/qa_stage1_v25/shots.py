"""v2.5 ステージ1（C案）の比較画像。ゲームのファイルは読むだけ（描画は本番の World.draw）。

    cd game
    python stages/qa_stage1_v25/shots.py

出力（このフォルダ）:
    gate1_before_after.png / gate2_before_after.png     城門: 改善前（通常の地面の描き方）と改善後（sealed_gate）
    gate1_zoom3x_before_after.png / gate2_zoom3x_...     同じ箇所の3倍拡大
    gate1_targets.png        ゲート1の前: 後ろの E02 と門の向こうの E03（両方に交換可能の印、E03 にカーソル）
    wall_start_compare.png   追跡壁 -600 / -450: 開始地点で1.8秒止まった時点と、ゲート1で2秒考えた時点
"""
import dataclasses
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests"))
os.chdir(GAME)

import pygame  # noqa: E402
from test_gameplay import DT, STAGE_1, InputState  # noqa: E402
import stage1_bot  # noqa: E402
from systems.world import World  # noqa: E402
from ui import fonts  # noqa: E402

pygame.init()
pygame.display.set_mode((960, 540))
PLAIN = dataclasses.replace(STAGE_1, platforms=tuple(dataclasses.replace(p, style="ground") for p in STAGE_1.platforms))
GATES = stage1_bot.gates(STAGE_1)


def label(s, text, pos=(8, 8), size=20, color=(255, 255, 255)):
    img = fonts.get_font(size, True).render(text, True, color)
    bg = pygame.Surface((img.get_width() + 14, img.get_height() + 8), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 180))
    s.blit(bg, pos); s.blit(img, (pos[0] + 7, pos[1] + 4))


def frame(stage, px, bottom=422.0, t=1.5, mouse_on=None):
    w = World(stage, with_graphics=True)
    w.wall.paused = True; w.wall.segments[0].front_x = -1e5
    p = w.player; p.rect.x = px; p.rect.bottom = bottom
    inp = InputState()
    for _ in range(int(t / DT)):
        if mouse_on:
            e = next((e for e in w.enemies if e.enemy_id == mouse_on), None)
            if e:
                inp.mouse_pos = w.camera.to_screen(*e.hurtbox.center)
        w.update(DT, inp); inp.clear_edges()
    s = pygame.Surface((960, 540)); w.draw(s)
    return s, w


def side_by_side(a, b, la, lb, name):
    a, b = a.copy(), b.copy()
    label(a, la); label(b, lb)
    out = pygame.Surface((a.get_width() * 2 + 8, a.get_height())); out.fill((255, 255, 255))
    out.blit(a, (0, 0)); out.blit(b, (a.get_width() + 8, 0))
    pygame.image.save(out, os.path.join(HERE, name))


# 1. 城門の改善前・改善後
for gid, (gl, gr, _) in GATES.items():
    px = gl - 24
    a, _ = frame(PLAIN, px)
    b, w = frame(STAGE_1, px)
    n = gid.lower().replace("gate", "gate")
    side_by_side(a, b, "改善前: 通常の地面と同じ描き方", "改善後: 崩落した城門＋異星の侵食（当たり判定は同じ）",
                 f"{n}_before_after.png")
    cx = (gl + gr) / 2 - w.camera.x
    crop = pygame.Rect(int(cx - 110), 180, 220, 280)
    side_by_side(pygame.transform.scale_by(a.subsurface(crop), 3), pygame.transform.scale_by(b.subsurface(crop), 3),
                 "改善前 ×3", "改善後 ×3", f"{n}_zoom3x_before_after.png")

# 2. ゲート1の前: E02 と E03
gl, gr, _ = GATES["GATE1"]
s, w = frame(STAGE_1, gl - 24, t=2.0, mouse_on="E03")
for eid, text in (("E02", "E02 後ろ（台座）: 見えて選べる"), ("E03", "E03 門の向こう: クリックで交換→門を越える")):
    e = next(e for e in w.enemies if e.enemy_id == eid)
    r = e.hurtbox.move(-w.camera.x, -w.camera.y).inflate(16, 30)
    pygame.draw.rect(s, (255, 230, 120), r, 2)
    label(s, text, (max(4, min(960 - 330, int(r.x) - 60)), int(r.y) - 40), size=16, color=(255, 230, 120))
gate = pygame.Rect(int(gl - w.camera.x), 0, int(gr - gl), 422)
pygame.draw.rect(s, (255, 120, 120), gate, 2)
label(s, "GATE1（通行不能・当たり判定の範囲）", (gate.x - 120, 60), size=16, color=(255, 150, 150))
label(s, "ゲート1の前で待機中（カーソルは E03 の上）")
pygame.image.save(s, os.path.join(HERE, "gate1_targets.png"))


# 3. 追跡壁 -600 / -450
def wall_frame(ws, *, stall=None, gate_wait=None):
    """stall: 開始地点で何もせず待つ秒数 / gate_wait: ダッシュなし・テレポートなしでゲート1に着いてから待つ秒数"""
    if stall is not None:
        w = World(STAGE_1, with_graphics=True)
        w.wall.segments[0].front_x = ws
        inp = InputState()
        for _ in range(int(round(stall / DT))):
            w.update(DT, inp); inp.clear_edges()
    else:
        arr = stage1_bot.play(STAGE_1, policy="none", dash=False, wall_start=ws, max_time=60).arrive["GATE1"][0]
        r = stage1_bot.play(STAGE_1, policy="none", dash=False, wall_start=ws, with_graphics=True,
                            max_time=arr + gate_wait)
        w = r.world
    s = pygame.Surface((960, 540)); w.draw(s)
    gap = w.player.rect.left - w.wall.front_x
    return s, gap, w.state


rows = []
for kw, title in ((dict(stall=1.8), "開始地点で 1.8 秒止まった時点"),
                  (dict(gate_wait=2.0), "ゲート1に着いて 2.0 秒考えた時点（ダッシュなし）")):
    pair = []
    for ws in (-600, -450):
        s, gap, state = wall_frame(ws, **kw)
        label(s, f"追跡壁の開始 {ws}px / {title}")
        label(s, f"壁との距離 {gap:.0f}px（あと {gap / STAGE_1.wall.speed:.2f} 秒）", (8, 44), size=18,
              color=(255, 200, 200))
        pair.append(s)
    rows.append(pair)
out = pygame.Surface((960 * 2 + 8, 540 * 2 + 8)); out.fill((255, 255, 255))
for i, pair in enumerate(rows):
    for j, s in enumerate(pair):
        out.blit(s, (j * 968, i * 548))
pygame.image.save(out, os.path.join(HERE, "wall_start_compare.png"))
print("saved to", HERE)
