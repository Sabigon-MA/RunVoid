"""近景装飾の配置（x のみ）の修正案を探す。背景素材・スプライトの切り出し・高さ（bottom）・数・種類は変えない。

    cd game
    set PYTHONPATH=stages\qa_stage1_v25 && python stages/qa_stage1_v25/deco_fix.py
        → deco_fix.txt / deco_fix_auto_candidate.json（自動探索の候補。本番には書き込まない）

各配置を単独で描いたときに、「進行方向に見えているとき」（対象の中心が画面 x 400〜960）の地形の輪郭を
どれだけ見えにくくするか（輪郭の消失率の増加の最大値）と、穴の口のすぐ上を覆う割合の最大値を「害」とし、
害が基準を超える配置だけを、害が基準未満になる最も近い x へ動かす（他の配置と 250px 以上離す）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
sys.argv = sys.argv[:1]
import pygame  # noqa: E402
import deco_audit as A  # noqa: E402  （同じフォルダ。読み込み時に現行配置の調査も走る）

bg, deco, terrain, EDGES = A.bg, A.deco, A.terrain, A.EDGES
CAMS = range(0, 2401, 16)
LIMIT_EDGE, LIMIT_MOUTH = 0.10, 0.30   # 重いものだけ直す（見た目の変更を最小にする）
MAX_MOVE, MIN_GAP, SAME_GAP = 600, 250, 700
period = deco.period or 1e9

# カメラごとの「装飾なしの背景」と「地形だけ（透明）」を先に作る
cache = {}
for cx in CAMS:
    b0 = pygame.Surface((960, 540)); saved = bg.decorations; bg.decorations = None; bg.draw(b0, cx); bg.decorations = saved
    t = pygame.Surface((960, 540), pygame.SRCALPHA); terrain.draw(t, A.Cam(cx))
    comp0 = b0.copy(); comp0.blit(t, (0, 0))
    cache[cx] = (b0, t, comp0)

PLACE = list(deco.items)


def harm(sprite, x, bottom):
    from stages.background import PlacementDef
    item = PlacementDef(sprite, x, bottom)
    img = deco.sprites[sprite]
    worst_edge, worst_mouth, where = 0.0, 0.0, None
    for cx in CAMS:
        rects = []
        for off in (-period, 0.0, period):
            sx, sy = deco.screen_pos(item, cx, off)
            r = pygame.Rect(sx, sy, img.get_width(), img.get_height())
            if r.right > 0 and r.left < 960:
                rects.append((sx, sy, r))
        if not rects:
            continue
        b0, t, comp0 = cache[cx]
        comp = None
        for name, pairs in EDGES.items():
            fx0, fx1 = A.feature_screen_x(name)
            if not 400 <= (fx0 + fx1) / 2 - cx <= 960:
                continue
            box = pygame.Rect(fx0 - cx - 45, 290, fx1 - fx0 + 90, 160)
            if not any(r.colliderect(box) for _, _, r in rects):
                continue
            if comp is None:
                comp = b0.copy()
                for sx, sy, _ in rects:
                    comp.blit(img, (sx, sy))
                comp.blit(t, (0, 0))
            l1 = l0 = n = 0
            for (ox, oy), (ix, iy) in pairs:
                a, b = int(ox - cx), int(ix - cx)
                if not (0 <= a < 960 and 0 <= b < 960):
                    continue
                n += 1
                l1 += abs(A.lum(comp.get_at((a, int(oy)))) - A.lum(comp.get_at((b, int(iy))))) < 18
                l0 += abs(A.lum(comp0.get_at((a, int(oy)))) - A.lum(comp0.get_at((b, int(iy))))) < 18
            if n and (l1 - l0) / n > worst_edge:
                worst_edge, where = (l1 - l0) / n, (name, cx)
        for x0, x1, top in terrain.pits:
            if not 400 <= (x0 + x1) / 2 - cx <= 960:
                continue
            cols = cov = 0
            for px in range(x0, x1, 2):
                s = px - cx
                if not 0 <= s < 960:
                    continue
                cols += 1
                for sx, sy, r in rects:
                    if r.left <= s < r.right and any(
                            0 <= yy - sy < img.get_height() and img.get_at((s - sx, yy - sy)).a >= 128
                            for yy in range(top - 24, top, 2)):
                        cov += 1
                        break
            if cols and cov / cols > worst_mouth:
                worst_mouth = cov / cols
                if worst_mouth > LIMIT_MOUTH:
                    where = (f"穴 {x0}-{x1} の口", cx)
    return worst_edge, worst_mouth, where


lines = ["# 近景装飾の配置修正の探索（進行方向に見えているときの害）",
         f"基準: 輪郭の消失率の増加 < {LIMIT_EDGE:.0%}、穴の口を覆う割合 < {LIMIT_MOUTH:.0%}、移動は ±{MAX_MOVE}px 以内、"
         f"他の配置と {MIN_GAP}px・同じ絵とは {SAME_GAP}px 以上離す"]
cur = []
for p in PLACE:
    e, m, wh = harm(p.sprite, p.x, p.bottom)
    cur.append((e, m))
    lines.append(f"現行 {p.sprite}@{p.x:.0f}: 輪郭 +{e:.0%} / 穴の口 {m:.0%}  最悪の場面 {wh}")

new_x = [p.x for p in PLACE]
for i, p in enumerate(PLACE):
    e, m = cur[i]
    if e < LIMIT_EDGE and m < LIMIT_MOUTH:
        continue
    best = None
    for d in sorted(range(-MAX_MOVE, MAX_MOVE + 1, 20), key=abs):
        x = (p.x + d) % period

        def dist(j):
            return min(abs(x - new_x[j]), period - abs(x - new_x[j]))
        if any(j != i and (dist(j) < MIN_GAP or (PLACE[j].sprite == p.sprite and dist(j) < SAME_GAP))
               for j in range(len(PLACE))):
            continue
        e2, m2, wh2 = harm(p.sprite, x, p.bottom)
        if e2 < LIMIT_EDGE and m2 < LIMIT_MOUTH:
            best = (x, d, e2, m2)
            break
    if best:
        new_x[i] = best[0]
        lines.append(f"→ {p.sprite}@{p.x:.0f} を x={best[0]:.0f}（{best[1]:+d}px）へ: 輪郭 +{best[2]:.0%} / 穴の口 {best[3]:.0%}")
    else:
        lines.append(f"→ {p.sprite}@{p.x:.0f}: ±{MAX_MOVE}px 以内に基準を満たす位置なし（そのまま）")

raw = json.load(open(os.path.join(GAME, "stages", "stage_1.json"), encoding="utf-8"))
pl = raw["background"]["decorations"]["placements"]
order = sorted(range(len(pl)), key=lambda k: pl[k]["x"])   # deco.items は x 順
for rank, k in enumerate(order):
    pl[k]["x"] = int(new_x[rank])
# 自動探索の結果（最終候補 deco_candidate_stage.json は、これに ruin_left 3050→2700・grass 2620→2360 を手で加えたもの。
# REPORT_followup.md の3章を参照）
with open(os.path.join(HERE, "deco_fix_auto_candidate.json"), "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False, indent=2)
print("\n".join(lines))
with open(os.path.join(HERE, "deco_fix.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
