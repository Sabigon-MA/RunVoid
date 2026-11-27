"""主人公のジャンプ到達高さ・飛距離を実コードで計測する（ステージは平地のみ）。"""
import os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.getcwd())
import pygame
pygame.init()
import config
from stages import parse_stage
from systems.world import World
from systems.input import InputState

DT = config.FIXED_DT
raw = {"spawn": {"x": 200, "y": 382}, "goal_x": 9000, "world_width": 9000,
       "wall": {"start_x": -99999, "speed": 0},
       "platforms": [{"id": "G", "x": 0, "y": 422, "w": 9000, "h": 118}]}
stage = parse_stage(raw)


def run(double=False, dash=False, run_right=True):
    w = World(stage, with_graphics=False)
    inp = InputState()
    p = w.player
    # 助走
    if run_right:
        inp.simulate_press("right")
    for _ in range(60):
        if w.update(DT, inp): inp.clear_edges()
    x0, top0 = p.rect.x, p.rect.bottom
    inp.simulate_press("jump")
    if w.update(DT, inp): inp.clear_edges()
    min_bottom, t, did2, didd = p.rect.bottom, 0, False, False
    while True:
        if double and not did2 and p.vy >= -30:
            inp.simulate_release("jump"); inp.simulate_press("jump"); did2 = True
        if dash and did2 and not didd and p.vy >= 0:
            inp.simulate_press("dash"); didd = True
        if w.update(DT, inp): inp.clear_edges()
        if didd: inp.simulate_release("dash")
        t += DT
        min_bottom = min(min_bottom, p.rect.bottom)
        if p.on_ground and t > 0.1:
            break
    return top0 - min_bottom, p.rect.x - x0, t


for label, kw in [("single", {}), ("double", {"double": True}), ("double+airdash", {"double": True, "dash": True})]:
    h, d, t = run(**kw)
    print(f"{label:16s} rise={h:6.1f}px  flat_distance={d:6.1f}px  airtime={t:5.2f}s")
