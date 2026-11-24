"""v3.0 の確認用スクリーンショット（game から実行: python stages/stage1_v3_design/shots.py）。

各地点に主人公を置き、追跡壁を止めてカメラを落ち着かせてから 1 枚ずつ保存し、一覧画像にまとめる。
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, GAME)
os.chdir(GAME)

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((960, 540))
from stages import load_stage  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import World  # noqa: E402
from ui.fonts import get_font  # noqa: E402

DT = 1 / 60
OUT = os.path.join(HERE, "shots")
os.makedirs(OUT, exist_ok=True)
stage = load_stage("stage_1_v3.json")

SPOTS = [
    ("01_start", "開始地点（中層）。上に屋根 R1・U1", 260, 422, 1.0),
    ("02_entrance_pit", "地下への入口（穴 760〜870、青緑）", 700, 422, 1.0),
    ("03_underground", "地下水路 D1。上に中層の E01", 1000, 742, 1.5),
    ("04_shaft_stairs", "竪穴の階段 ST1・ST2 と影翔け F1", 1360, 636, 1.5),
    ("05_upper_U1", "上層 U1。下に中層・B01", 1150, 182, 1.5),
    ("06_upper_U3_F2", "上層 U3 と影翔け F2（隙間の上空）", 1980, 160, 1.5),
    ("07_gate1_mid", "GATE1 前（中層）。向こうに E03・EU3", 2290, 422, 1.5),
    ("08_death_pit", "落とし穴（穴 2900〜2980、赤）と影翔け F3", 2860, 438, 1.5),
    ("09_gate2_upper", "GATE2 前（上層 U6）。向こうに EU4", 3010, 222, 1.5),
]


def shot(name, label, x, foot, settle):
    w = World(stage)
    w.wall.paused = True
    w.wall.segments[0].front_x = -1e5
    w.player.place_foot(x, foot)
    w.player.invuln = 99
    w.camera.snap_to(w.player.rect)
    inp = InputState()
    for _ in range(int(settle / DT)):
        w.update(DT, inp)
        inp.clear_edges()
    w.player.invuln = 0.0          # 無敵中の点滅で主人公が消えた状態を撮らないように
    surf = pygame.Surface((960, 540))
    w.draw(surf)
    font = get_font(16)
    bg = pygame.Surface((960, 26), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 170))
    surf.blit(bg, (0, 0))
    surf.blit(font.render(f"{name}  {label}   camera=({w.camera.x:.0f},{w.camera.y:.0f})", True, (240, 235, 225)), (8, 4))
    pygame.image.save(surf, os.path.join(OUT, f"{name}.png"))
    return surf


thumbs = [shot(*s) for s in SPOTS]
cols, tw, th = 3, 480, 270
sheet = pygame.Surface((cols * tw, (len(thumbs) + cols - 1) // cols * th))
for i, t in enumerate(thumbs):
    sheet.blit(pygame.transform.smoothscale(t, (tw, th)), ((i % cols) * tw, (i // cols) * th))
pygame.image.save(sheet, os.path.join(OUT, "contact_sheet.png"))
print("saved", len(thumbs), "shots to", OUT)
