"""近景装飾（L3_near_debris、旧配置のまま）と v2.5 の新地形の位置関係の調査。

    cd game
    python stages/qa_stage1_v25/deco_audit.py [stage.json]   → deco_audit.txt / deco_audit.json / deco_worst_*.png

近景装飾は地形より奥（地形の前に描く背景の一部）で、factor 0.75 で動くため、カメラ位置によって地形との重なりが変わる。
地形の当たり判定とは無関係（描画のみ）。穴の内部（y≥422）は穴の絵が不透明に覆うので、影響があるのは y<422 だけ。

指標（カメラ x を 0〜2400 で 8px おきに動かして測る）:
  輪郭の消失率: 地形の輪郭の外側1〜3px（空気側）と内側1〜3px（地形側）の明るさの差が 18 未満の画素の割合。
               装飾あり／なしの差 = 装飾が輪郭を見えにくくした分
    - 穴の縁: 穴の左右の地面の角（上面と、穴に面した側面の上部 0〜24px）
    - 高い足場: S01・B01・PED の上面と側面
    - 降り段: G02s・G04s の段差（16px）の面と、段の上面
  穴の口の装飾率: 穴の幅のうち、穴の口のすぐ上（y 398〜421）に不透明な装飾（α≥128）がある列の割合（穴をまたぐ地面に見える恐れ）
  「進行方向に見えているとき」= 対象が主人公より前（画面 x 400〜960）にあるカメラ位置だけで集計した値も出す。
"""
import json
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
from ui import fonts  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
STAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "stage_1.json"
TAG = os.path.splitext(os.path.basename(STAGE_PATH))[0]
stage = load_stage(STAGE_PATH)
bg = ParallaxImageBackground(stage.background, 960, 540)
deco = bg.decorations
terrain = TerrainRenderer(stage)
P = {p.id: p for p in stage.platforms}
GROUND = 422


class Cam:
    def __init__(self, x):
        self.x, self.y = float(x), 0.0

    @property
    def view_rect(self):
        return pygame.Rect(int(self.x), 0, 960, 540)


def edges():
    """{名前: [(外側の点, 内側の点), ...]}（ワールド座標）"""
    out = {}
    for x0, x1, top in terrain.pits:
        pairs = []
        for d in range(1, 4):
            for x in range(x0 - 40, x0):            # 左岸の上面
                pairs.append(((x, top - d), (x, top + d)))
            for x in range(x1, x1 + 40):            # 右岸の上面
                pairs.append(((x, top - d), (x, top + d)))
            for y in range(top, top + 24):           # 穴に面した側面
                pairs.append(((x0 - 1 + d, y), (x0 - d, y)))
                pairs.append(((x1 - d, y), (x1 - 1 + d, y)))
        out[f"穴 {x0}-{x1}"] = pairs
    for pid in ("S01", "B01", "PED"):
        p = P[pid]
        pairs = []
        for d in range(1, 4):
            for x in range(int(p.x), int(p.x + p.w)):
                pairs.append(((x, p.y - d), (x, p.y + d)))
            for y in range(int(p.y), GROUND):
                pairs.append(((p.x - d, y), (p.x - 1 + d, y)))
                pairs.append(((p.x + p.w - 1 + d, y), (p.x + p.w - d, y)))
        out[f"足場 {pid}"] = pairs
    for pid, upper in (("G02s", "G02"), ("G04s", "G04")):
        s = P[pid]
        pairs = []
        for d in range(1, 4):
            for y in range(GROUND, int(s.y)):        # 段差の面（上の地面の右側面）
                pairs.append(((s.x - 1 + d, y), (s.x - d, y)))
            for x in range(int(s.x), int(s.x + s.w)):
                pairs.append(((x, s.y - d), (x, s.y + d)))
        out[f"降り段 {pid}"] = pairs
    return out


EDGES = edges()


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def compose(cx, with_deco):
    s = pygame.Surface((960, 540))
    saved = bg.decorations
    if not with_deco:
        bg.decorations = None
    bg.draw(s, cx)
    bg.decorations = saved
    terrain.draw(s, Cam(cx))
    return s


def deco_alpha(cx):
    a = pygame.Surface((960, 540), pygame.SRCALPHA)
    deco.draw(a, cx)
    return a


def feature_screen_x(name):
    if name.startswith("穴"):
        a, b = map(int, name.split()[1].split("-"))
        return a, b
    p = P[name.split()[1]]
    return p.x, p.x + p.w


results = {k: [] for k in EDGES}
mouths = {f"穴 {x0}-{x1}": [] for x0, x1, _ in terrain.pits}
for cx in range(0, 2401, 8):
    s1 = s0 = al = None
    for name, pairs in EDGES.items():
        fx0, fx1 = feature_screen_x(name)
        if fx1 - cx < 0 or fx0 - cx > 960:
            continue
        if s1 is None:
            s1, s0, al = compose(cx, True), compose(cx, False), deco_alpha(cx)
        lost1 = lost0 = n = 0
        for (ox, oy), (ix, iy) in pairs:
            sx, sxi = int(ox - cx), int(ix - cx)
            if not (0 <= sx < 960 and 0 <= sxi < 960 and 0 <= oy < 540 and 0 <= iy < 540):
                continue
            n += 1
            lost1 += abs(lum(s1.get_at((sx, int(oy)))) - lum(s1.get_at((sxi, int(iy))))) < 18
            lost0 += abs(lum(s0.get_at((sx, int(oy)))) - lum(s0.get_at((sxi, int(iy))))) < 18
        if n:
            ahead = 400 <= (fx0 + fx1) / 2 - cx <= 960
            results[name].append((cx, lost1 / n, lost0 / n, ahead))
    for x0, x1, top in terrain.pits:
        if x1 - cx < 0 or x0 - cx > 960 or al is None:
            continue
        cols = covered = 0
        for x in range(x0, x1):
            sx = x - cx
            if 0 <= sx < 960:
                cols += 1
                covered += any(al.get_at((sx, y)).a >= 128 for y in range(top - 24, top))
        if cols:
            mouths[f"穴 {x0}-{x1}"].append((cx, covered / cols, 400 <= (x0 + x1) / 2 - cx <= 960))

lines = [f"# 近景装飾の調査（{STAGE_PATH}）", "輪郭の消失率 = 外側と内側の明るさの差が18未満の画素の割合（装飾あり / なし）"]
summary = {}
for name, rows in results.items():
    if not rows:
        continue
    worst = max(rows, key=lambda r: r[1] - r[2])
    ah = [r for r in rows if r[3]]
    worst_ahead = max(ah, key=lambda r: r[1] - r[2]) if ah else None
    mean_inc = sum(r[1] - r[2] for r in rows) / len(rows)
    summary[name] = dict(worst_cam=worst[0], worst_with=worst[1], worst_without=worst[2], mean_increase=mean_inc,
                         worst_ahead=worst_ahead)
    lines.append(f"{name}: 最悪 カメラx={worst[0]} で {worst[1]:.0%}（装飾なし {worst[2]:.0%}）、平均の増加 {mean_inc:+.1%}"
                 + (f" / 進行方向で最悪 カメラx={worst_ahead[0]} {worst_ahead[1]:.0%}（なし {worst_ahead[2]:.0%}）" if worst_ahead else ""))
lines.append("穴の口のすぐ上（y 398〜421）に不透明な装飾がある列の割合")
for name, rows in mouths.items():
    if not rows:
        continue
    worst = max(rows, key=lambda r: r[1])
    ah = [r for r in rows if r[2]]
    wa = max(ah, key=lambda r: r[1]) if ah else None
    summary[name + " 口"] = dict(worst_cam=worst[0], worst=worst[1], worst_ahead=wa)
    lines.append(f"{name}: 最悪 カメラx={worst[0]} で {worst[1]:.0%}" + (f" / 進行方向で最悪 カメラx={wa[0]} {wa[1]:.0%}" if wa else ""))
print("\n".join(lines))
with open(os.path.join(HERE, f"deco_audit_{TAG}.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
with open(os.path.join(HERE, f"deco_audit_{TAG}.json"), "w", encoding="utf-8") as f:
    json.dump(dict(summary=summary, results=results, mouths=mouths), f, ensure_ascii=False)

# 最悪の場面の画像（装飾あり／なし、対象の周りを2倍）
shots = []
for name, sm in summary.items():
    if name.endswith(" 口"):
        continue
    if sm["worst_with"] - sm["worst_without"] < 0.10:
        continue
    cx = sm["worst_cam"]
    fx0, fx1 = feature_screen_x(name)
    mid = int((fx0 + fx1) / 2 - cx)
    crop = pygame.Rect(max(0, min(960 - 320, mid - 160)), 250, 320, 220)
    a = pygame.transform.scale_by(compose(cx, True).subsurface(crop), 2)
    b = pygame.transform.scale_by(compose(cx, False).subsurface(crop), 2)
    row = pygame.Surface((a.get_width() * 2 + 8, a.get_height())); row.fill((255, 255, 255))
    row.blit(a, (0, 0)); row.blit(b, (a.get_width() + 8, 0))
    for txt, x in ((f"{name} 装飾あり（カメラx={cx}）{sm['worst_with']:.0%}", 0),
                   (f"装飾なし {sm['worst_without']:.0%}", a.get_width() + 8)):
        img = fonts.get_font(16, True).render(txt, True, (255, 255, 255))
        bgs = pygame.Surface((img.get_width() + 10, img.get_height() + 6), pygame.SRCALPHA); bgs.fill((0, 0, 0, 190))
        row.blit(bgs, (x + 6, 6)); row.blit(img, (x + 11, 9))
    shots.append(row)
if shots:
    out = pygame.Surface((shots[0].get_width(), sum(s.get_height() + 8 for s in shots))); out.fill((255, 255, 255))
    y = 0
    for s in shots:
        out.blit(s, (0, y)); y += s.get_height() + 8
    pygame.image.save(out, os.path.join(HERE, f"deco_worst_{TAG}.png"))
    print("→", f"deco_worst_{TAG}.png")
