"""チェックポイントの目印: 通過前（未起動）・起動の瞬間・起動後0.37秒・再開直後の比較画像（拡大は未起動・起動の瞬間・起動済み）。

    cd game
    python stages/qa_stage1_v25/checkpoint_shots.py   → checkpoint_marker.png / checkpoint_marker_zoom.png

実際のゲームと同じ World を使い、主人公を G03 の上で右へ走らせて x=1,560 を通過させる（壁は止めて画面外へ）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import pygame  # noqa: E402
from test_gameplay import DT, STAGE_1  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import World  # noqa: E402
from ui import fonts  # noqa: E402
from ui.hud import HUD  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
CP = STAGE_1.checkpoint


def label(s, text):
    img = fonts.get_font(18, True).render(text, True, (255, 255, 255))
    b = pygame.Surface((img.get_width() + 14, img.get_height() + 8), pygame.SRCALPHA); b.fill((0, 0, 0, 190))
    s.blit(b, (8, 498)); s.blit(img, (15, 502))


def shot(w, text, hud=False):
    s = pygame.Surface((960, 540))
    w.draw(s)
    if hud:
        HUD().draw(s, w)
    label(s, text)
    return s


shots = []
w = World(STAGE_1)
w.wall.paused = True; w.wall.segments[0].front_x = -1e5
w.player.rect.topleft = (1420 + 120, 382)       # G03 の左端付近（チェックポイントの手前）
w.player.rect.x = 1450 + 80
w.camera.snap_to(w.player.rect)
inp = InputState()
for _ in range(10):
    w.update(DT, inp)
shots.append(shot(w, f"通過前（未起動）  主人公 x={w.player.rect.x:.0f}"))
inp.simulate_press("right")
frames = 0
while not w.checkpoint_lit:
    w.update(DT, inp); inp.clear_edges(); frames += 1
w.update(DT, inp); inp.clear_edges()
inp.simulate_release("right")
shots.append(shot(w, "起動の瞬間（0.03秒）: 光の柱と地面の輪"))
for _ in range(20):
    w.update(DT, inp)
shots.append(shot(w, "起動から0.37秒"))
r = World(STAGE_1, from_checkpoint=True)
for _ in range(6):
    r.update(DT, InputState())
shots.append(shot(r, "チェックポイントから再開した直後（起動済み・HUD 表示）", hud=True))

out = pygame.Surface((960 * 2 + 8, 540 * 2 + 8)); out.fill((255, 255, 255))
for i, s in enumerate(shots):
    out.blit(s, ((i % 2) * 968, (i // 2) * 548))
pygame.image.save(out, os.path.join(HERE, "checkpoint_marker.png"))

# 拡大（3倍）: 未起動 / 起動の瞬間 / 起動済み（主人公は写さない位置にカメラを置く）
zoom = pygame.Surface((3 * 130 * 3 + 16, 110 * 3)); zoom.fill((255, 255, 255))
crops = []
w2 = World(STAGE_1)
w2.wall.paused = True; w2.wall.segments[0].front_x = -1e5
w2.player.rect.x = 1300; w2.camera.snap_to(w2.player.rect)
for state in ("unlit", "flash", "lit"):
    if state == "flash":
        w2.terrain_renderer.set_checkpoint_lit(flash=True)
        w2.terrain_renderer.checkpoint_age = 0.12
    elif state == "lit":
        w2.terrain_renderer.checkpoint_age = 5.0
    s = pygame.Surface((960, 540)); w2.draw(s)
    x = int(CP.x - w2.camera.x)
    crops.append(s.subsurface((x - 65, 422 - 90, 130, 110)).copy())
for i, c in enumerate(crops):
    zoom.blit(pygame.transform.scale(c, (390, 330)), (i * 398, 0))
pygame.image.save(zoom, os.path.join(HERE, "checkpoint_marker_zoom.png"))
print("saved", frames)
