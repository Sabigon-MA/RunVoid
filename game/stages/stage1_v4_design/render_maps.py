"""v4.0 設計案の地図画像を描く（全体図・エリアごとの拡大図）。v4data / verify / estimate のデータを直接使う。

game フォルダから実行する: python stages/stage1_v4_design/render_maps.py
出力: stages/stage1_v4_design/maps/*.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.getcwd())
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pygame  # noqa: E402

pygame.init()
from ui.fonts import get_font  # noqa: E402

import v4data as D  # noqa: E402
from estimate import ROUTES, VZONES  # noqa: E402
from verify import SWAPS  # noqa: E402

OUT = HERE / "maps"
BG = (18, 16, 22)
GRID = (40, 38, 48)
GRID_TXT = (110, 104, 120)
LAYER_COL = {D.UPPER: (150, 120, 92), D.MID: (112, 96, 84), D.LOWER: (78, 92, 100), D.DEEP: (52, 92, 96),
             "gate": (40, 170, 160)}
ONEWAY_COL = (196, 168, 120)
ROUTE_COL = {"上層": (255, 196, 70), "中層": (120, 200, 255), "地下": (110, 230, 150), "熟練": (255, 110, 200)}
ENEMY_COL = {"shadow_crawler": (200, 90, 255), "shadow_flier": (255, 120, 160)}
CP_COL = (170, 160, 255)
KILL_COL = (150, 20, 30)
TELE_COL = (215, 70, 235)
T = {t["id"]: t for t in D.TERRAIN}
E = {e[0]: e for e in D.ENEMIES}


class View:
    def __init__(self, x0, x1, y0, y1, scale, pad=(70, 40, 30, 60)):
        self.x0, self.x1, self.y0, self.y1, self.s = x0, x1, y0, y1, scale
        self.pl, self.pt, self.pr, self.pb = pad
        self.w = int((x1 - x0) * scale) + self.pl + self.pr
        self.h = int((y1 - y0) * scale) + self.pt + self.pb

    def p(self, x, y):
        return (self.pl + (x - self.x0) * self.s, self.pt + (y - self.y0) * self.s)

    def r(self, x0, y0, x1, y1):
        a, b = self.p(max(x0, self.x0 - 50), max(y0, self.y0 - 50)), self.p(min(x1, self.x1 + 50), min(y1, self.y1 + 50))
        return pygame.Rect(round(a[0]), round(a[1]), max(1, round(b[0] - a[0])), max(1, round(b[1] - a[1])))


def text(surf, s, pos, size=13, col=(230, 222, 210), bold=False, anchor="topleft", bg=None):
    img = get_font(size, bold).render(s, True, col)
    rect = img.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
    if bg:
        pygame.draw.rect(surf, bg, rect.inflate(6, 2))
    surf.blit(img, rect)
    return rect


def draw_grid(surf, v, step_x, step_y, labels=True):
    x = (v.x0 // step_x) * step_x
    while x <= v.x1:
        a, b = v.p(x, v.y0), v.p(x, v.y1)
        pygame.draw.line(surf, GRID, a, b, 1)
        if labels:
            text(surf, f"{x}", (a[0], b[1] + 4), 11, GRID_TXT, anchor="midtop")
        x += step_x
    y = (v.y0 // step_y) * step_y
    while y <= v.y1:
        a, b = v.p(v.x0, y), v.p(v.x1, y)
        pygame.draw.line(surf, GRID, a, b, 1)
        if labels:
            text(surf, f"y={y}", (a[0] - 6, a[1]), 11, GRID_TXT, anchor="midright")
        y += step_y
    # 落下死ライン
    ky = v.p(v.x0, D.KILL_Y)[1]
    if v.pt <= ky <= v.h:
        pygame.draw.line(surf, KILL_COL, (v.pl, ky), (v.w - v.pr, ky), 2)


def draw_terrain(surf, v, ids=False, size=11):
    # 落とし穴（地形のない列が落下死ラインまで続く場所）を赤く塗る
    for t in D.TERRAIN:
        if t["kind"] == "oneway":
            continue
        rect = v.r(t["x0"], t["top"], t["x1"], t["bottom"])
        col = LAYER_COL.get(t["layer"], (100, 100, 100))
        if t["style"] == "sealed_gate":
            rect = v.r(t["x0"], max(t["top"], v.y0), t["x1"], t["bottom"])
            pygame.draw.rect(surf, (20, 60, 60), rect)
            for yy in range(rect.top, rect.bottom, 10):
                pygame.draw.line(surf, col, (rect.left, yy), (rect.right, yy + 5), 1)
            pygame.draw.rect(surf, col, rect, 2)
        else:
            pygame.draw.rect(surf, col, rect)
            top = v.r(t["x0"], t["top"], t["x1"], t["top"] + 3 / v.s)
            pygame.draw.rect(surf, tuple(min(255, c + 60) for c in col), top)
    for t in D.TERRAIN:
        if t["kind"] != "oneway":
            continue
        rect = v.r(t["x0"], t["top"], t["x1"], t["top"] + max(16, 4 / v.s))
        pygame.draw.rect(surf, ONEWAY_COL, rect)
        for xx in range(rect.left + 2, rect.right, 8):
            pygame.draw.line(surf, (90, 70, 50), (xx, rect.top), (xx, rect.bottom), 1)
    if ids:
        for t in D.TERRAIN:
            if t["style"] == "sealed_gate":
                x, y = v.p((t["x0"] + t["x1"]) / 2, max(v.y0, 0) + 30)
                text(surf, t["id"], (x, y), size + 1, (120, 255, 240), True, "midtop", bg=(10, 30, 30))
                continue
            x, y = v.p((t["x0"] + t["x1"]) / 2, t["top"])
            if v.x0 - 20 <= (t["x0"] + t["x1"]) / 2 <= v.x1 + 20:
                text(surf, f"{t['id'][2:]} {t['top']}", (x, y - 2), size, (240, 232, 214), anchor="midbottom",
                     bg=(24, 20, 26))


def draw_pits(surf, v):
    """落とし穴（落下死）の位置に赤い印を描く。地形のない列が落下死ラインまで続く x の範囲を探す。"""
    solids = [t for t in D.TERRAIN if t["kind"] == "solid"]
    x = max(0, v.x0)
    start = None
    while x <= min(D.WORLD_W, v.x1):
        open_col = not any(t["x0"] <= x < t["x1"] and t["bottom"] >= D.WORLD_BOTTOM for t in solids)
        if open_col and start is None:
            start = x
        if (not open_col or x >= min(D.WORLD_W, v.x1)) and start is not None:
            a, b = v.p(start, D.WORLD_BOTTOM - 40), v.p(x, D.WORLD_BOTTOM)
            pygame.draw.rect(surf, KILL_COL, pygame.Rect(round(a[0]), round(a[1]), max(2, round(b[0] - a[0])),
                                                         max(2, round(b[1] - a[1]))))
            start = None
        x += 10


def draw_enemies(surf, v, labels=True, size=12):
    for eid, ty, x, fy, area, role in D.ENEMIES:
        if not (v.x0 - 40 <= x <= v.x1 + 40):
            continue
        col = ENEMY_COL[ty]
        cx, cy = v.p(x, fy)
        r = max(4, 18 * v.s)
        if ty == "shadow_crawler":
            pygame.draw.ellipse(surf, col, pygame.Rect(cx - r, cy - r * 1.1, r * 2, r * 1.1))
        else:
            pts = [(cx - r * 1.4, cy - r * 1.2), (cx, cy - r * 0.2), (cx + r * 1.4, cy - r * 1.2), (cx, cy - r * 0.7)]
            pygame.draw.polygon(surf, col, pts)
        if labels:
            text(surf, eid, (cx, cy - r * 1.3 - 2), size, col, True, "midbottom")


def draw_checkpoints(surf, v, labels=True):
    for cid, cx, (sx, sy), _ in D.CHECKPOINTS:
        a, b = v.p(cx, D.WORLD_TOP), v.p(cx, D.WORLD_BOTTOM)
        for yy in range(int(a[1]), int(b[1]), 12):
            pygame.draw.line(surf, CP_COL, (a[0], yy), (a[0], yy + 6), 1)
        p = v.p(sx, sy)
        pygame.draw.polygon(surf, CP_COL, [(p[0], p[1] - 22), (p[0] + 12, p[1] - 16), (p[0], p[1] - 10)])
        pygame.draw.line(surf, CP_COL, (p[0], p[1]), (p[0], p[1] - 22), 2)
        if labels:
            text(surf, cid, (p[0] + 4, p[1] - 24), 13, CP_COL, True, "bottomleft")


def draw_route(surf, v, name, width=3, offset=0):
    col = ROUTE_COL[name]
    pts = [(D.SPAWN[0], D.SPAWN[1])] + [(l[1], l[2]) for l in ROUTES[name]]
    ops = ["start"] + [l[0] for l in ROUTES[name]]
    for (a, b, op) in zip(pts, pts[1:], ops[1:]):
        pa, pb = v.p(a[0], a[1] - 20 + offset), v.p(b[0], b[1] - 20 + offset)
        if op.startswith("tp"):
            # テレポートは点線（必須は太く）
            n = max(2, int(((pb[0] - pa[0]) ** 2 + (pb[1] - pa[1]) ** 2) ** 0.5 / 8))
            for k in range(0, n, 2):
                q0 = (pa[0] + (pb[0] - pa[0]) * k / n, pa[1] + (pb[1] - pa[1]) * k / n)
                q1 = (pa[0] + (pb[0] - pa[0]) * (k + 1) / n, pa[1] + (pb[1] - pa[1]) * (k + 1) / n)
                pygame.draw.line(surf, TELE_COL, q0, q1, width + (1 if "!" in op else 0))
        else:
            pygame.draw.line(surf, col, pa, pb, width)


def draw_vzones(surf, v):
    for z in VZONES:
        if z["x1"] < v.x0 or z["x0"] > v.x1:
            continue
        rect = v.r(z["x0"], z["top"], z["x1"], z["floor"])
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((200, 40, 40, 34))
        surf.blit(s, rect)
        pygame.draw.rect(surf, (200, 60, 60), rect, 1)
        text(surf, f"{z['id']} 潮（D案）↑{int(z['speed'])}px/s", (rect.left + 4, rect.bottom - 4), 12,
             (255, 140, 140), anchor="bottomleft")


def legend(surf, x, y, items):
    for label, col, kind in items:
        if kind == "line":
            pygame.draw.line(surf, col, (x, y + 8), (x + 26, y + 8), 3)
        elif kind == "dash":
            for k in range(0, 26, 8):
                pygame.draw.line(surf, col, (x + k, y + 8), (x + k + 4, y + 8), 3)
        else:
            pygame.draw.rect(surf, col, (x, y + 2, 26, 12))
        r = text(surf, label, (x + 32, y), 13)
        x = r.right + 18
    return y + 20


LEGEND = [("上層ルート", ROUTE_COL["上層"], "line"), ("中層ルート", ROUTE_COL["中層"], "line"),
          ("地下ルート", ROUTE_COL["地下"], "line"), ("熟練", ROUTE_COL["熟練"], "line"),
          ("テレポート", TELE_COL, "dash"), ("すり抜け足場", ONEWAY_COL, "box"), ("城門・侵食の柱", LAYER_COL["gate"], "box"),
          ("落とし穴・落下死ライン", KILL_COL, "box"), ("影這い", ENEMY_COL["shadow_crawler"], "box"),
          ("影翔け", ENEMY_COL["shadow_flier"], "box"), ("チェックポイント", CP_COL, "box")]


def overview():
    v = View(0, D.WORLD_W, D.WORLD_TOP, D.KILL_Y + 20, 0.25, pad=(70, 80, 30, 90))
    surf = pygame.Surface((v.w, v.h))
    surf.fill(BG)
    draw_grid(surf, v, 720, 200)
    for a, x0, x1, name, theme in D.AREAS:
        p0, p1 = v.p(x0, D.WORLD_TOP), v.p(x1, D.WORLD_TOP)
        pygame.draw.line(surf, (90, 84, 110), (p0[0], v.pt - 30), (p0[0], v.h - v.pb), 1)
        text(surf, f"{a} {name}", ((p0[0] + p1[0]) / 2, v.pt - 28), 14, (240, 228, 200), True, "midtop")
    draw_vzones(surf, v)
    draw_terrain(surf, v)
    draw_pits(surf, v)
    for i, name in enumerate(("地下", "中層", "上層")):
        draw_route(surf, v, name, 2, offset=-6 * i)
    draw_checkpoints(surf, v)
    draw_enemies(surf, v, labels=True, size=11)
    text(surf, "ステージ1 v4.0 設計案 全体図（1px = 4px、縦横同じ縮尺）  幅 10,080 × 高さ 1,400、地形の上面 y=190〜1,300（高低差 1,110）",
         (v.pl, 10), 16, (255, 240, 220), True)
    gl = v.p(D.GOAL_X, 560)
    pygame.draw.line(surf, (255, 255, 255), (gl[0], gl[1] - 60), (gl[0], gl[1]), 2)
    text(surf, "ゴール → ボス闘技場", (gl[0] - 4, gl[1] - 62), 12, (255, 255, 255), anchor="bottomright")
    legend(surf, v.pl, v.h - 34, LEGEND)
    pygame.image.save(surf, str(OUT / "00_overview.png"))


def area_map(idx):
    a, x0, x1, name, theme = D.AREAS[idx]
    ys = [t["top"] for t in D.TERRAIN if t["x1"] > x0 - 80 and t["x0"] < x1 + 80 and t["style"] != "sealed_gate"]
    ys += [fy for _, _, x, fy, *_ in D.ENEMIES if x0 - 80 <= x <= x1 + 80]
    y0 = max(D.WORLD_TOP - 40, min(ys) - 160)
    y1 = min(D.KILL_Y + 20, max(ys) + 180)
    v = View(x0 - 120, x1 + 120, y0, y1, 0.6, pad=(70, 70, 30, 120))
    surf = pygame.Surface((v.w, v.h))
    surf.fill(BG)
    draw_grid(surf, v, 120, 100)
    for b, bx0, bx1, *_ in D.AREAS:
        for bx in (bx0, bx1):
            if v.x0 <= bx <= v.x1:
                p = v.p(bx, v.y0)
                pygame.draw.line(surf, (110, 100, 140), p, (p[0], v.h - v.pb), 2)
    draw_vzones(surf, v)
    draw_terrain(surf, v, ids=True, size=11)
    draw_pits(surf, v)
    for i, rn in enumerate(("地下", "中層", "上層", "熟練")):
        draw_route(surf, v, rn, 3, offset=-5 * i)
    # この区間の交換（任意は細い、必須は太い）
    for frm, sx, tgt, follow, to, req in SWAPS:
        e = E[tgt]
        if not (x0 - 120 <= sx <= x1 + 120):
            continue
        a_, b_ = v.p(sx, T[frm]["top"] - 20), v.p(e[2], e[3] - 11)
        pygame.draw.line(surf, TELE_COL, a_, b_, 3 if req else 1)
        pygame.draw.circle(surf, TELE_COL, a_, 4)
        mid = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
        text(surf, ("必須" if req else "任意") + f" ⇄{tgt}", mid, 12, TELE_COL, True, "center", bg=(20, 10, 24))
    draw_checkpoints(surf, v)
    draw_enemies(surf, v, labels=True, size=13)
    text(surf, f"{a} {name}  x={x0}〜{x1}", (v.pl, 8), 20, (255, 240, 220), True)
    text(surf, theme, (v.pl, 36), 14, (220, 210, 190))
    # 下に、この区間の敵の役割
    yy = v.h - v.pb + 26
    for eid, ty, x, fy, ar, role in D.ENEMIES:
        if ar == a:
            text(surf, f"{eid}（{'影翔け' if ty == 'shadow_flier' else '影這い'} x={x}, y={fy}）: {role}",
                 (v.pl, yy), 12, ENEMY_COL[ty])
            yy += 17
    if yy > v.h - 4:
        big = pygame.Surface((v.w, yy + 8))
        big.fill(BG)
        big.blit(surf, (0, 0))
        surf = big
        yy2 = v.h - v.pb + 26
        for eid, ty, x, fy, ar, role in D.ENEMIES:
            if ar == a:
                text(surf, f"{eid}（{'影翔け' if ty == 'shadow_flier' else '影這い'} x={x}, y={fy}）: {role}",
                     (v.pl, yy2), 12, ENEMY_COL[ty])
                yy2 += 17
    pygame.image.save(surf, str(OUT / f"{idx + 1:02d}_{a}.png"))


def main():
    OUT.mkdir(exist_ok=True)
    overview()
    for i in range(len(D.AREAS)):
        area_map(i)
    print("saved", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
