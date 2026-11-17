"""近景装飾の配置: 旧配置と現在の stage_1.json（反映後）の比較画像。

    cd game
    python stages/qa_stage1_v25/deco_shots.py   → deco_before_after.png

背景＋地形＋主人公（カメラ位置に合う場所に立たせる）だけを描く。敵・追跡壁は描かない。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import pygame  # noqa: E402
from stages import load_stage  # noqa: E402
from stages.background import ParallaxImageBackground  # noqa: E402
from stages.renderer import TerrainRenderer  # noqa: E402
from player import create_protagonist  # noqa: E402
from ui import fonts  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
CASES = [(2296, "穴 2,900 と降り段 G04s に近づくところ"), (1920, "ゲート1の前で考えているとき（G04s が見える）"),
         (576, "B01 の手前（降り段 G02s が前方）"), (744, "穴 1,300 の手前（奥に目印）"),
         (1250, "チェックポイントの目印（未起動）が主人公の左後方に見える"), (2400, "ゴール付近（カメラの右端）")]


class Cam:
    def __init__(self, x):
        self.x, self.y = float(x), 0.0

    @property
    def view_rect(self):
        return pygame.Rect(int(self.x), 0, 960, 540)


def render(stage, cx):
    bg = ParallaxImageBackground(stage.background, 960, 540)
    tr = TerrainRenderer(stage)
    s = pygame.Surface((960, 540))
    bg.draw(s, cx)
    tr.draw(s, Cam(cx))
    p = create_protagonist(cx + 384 - 12, 382)
    ground = min((q.y for q in stage.platforms if q.x <= p.rect.centerx < q.x + q.w), default=422)
    p.rect.bottom = ground
    p.draw(s, Cam(cx))
    return s


def label(s, text, pos=(8, 8)):
    img = fonts.get_font(18, True).render(text, True, (255, 255, 255))
    b = pygame.Surface((img.get_width() + 14, img.get_height() + 8), pygame.SRCALPHA); b.fill((0, 0, 0, 185))
    s.blit(b, pos); s.blit(img, (pos[0] + 7, pos[1] + 4))


# 反映後（2026-11-17）: 左 = 旧配置（現在の stage_1.json の配置 x だけを元に戻したもの）、右 = 現在の stage_1.json
import json  # noqa: E402
from stages.loader import STAGE_DIR, parse_stage  # noqa: E402
OLD_X = {("grass", 1600): 1400, ("grass", 2360): 2620, ("ruin_left", 2700): 3050}
raw = json.load(open(STAGE_DIR / "stage_1.json", encoding="utf-8"))
for p in raw["background"]["decorations"]["placements"]:
    p["x"] = OLD_X.get((p["sprite"], p["x"]), p["x"])
cur = parse_stage(raw)
cand = load_stage("stage_1.json")
H = 300   # 下側だけ（地形と装飾が重なる高さ）
out = pygame.Surface((960 * 2 + 8, (H + 8) * len(CASES))); out.fill((255, 255, 255))
for i, (cx, title) in enumerate(CASES):
    for j, (st, name) in enumerate(((cur, "旧配置"), (cand, "現在（反映後）"))):
        s = render(st, cx).subsurface((0, 540 - H, 960, H)).copy()
        label(s, f"{name} / カメラx={cx}: {title}")
        out.blit(s, (j * 968, i * (H + 8)))
pygame.image.save(out, os.path.join(HERE, "deco_before_after.png"))
print("saved deco_before_after.png")
