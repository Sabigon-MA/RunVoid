"""v3.0 のレーン図（ASCII）と、跳躍の到達可能性・縦方向の視認性の確認。

stages/stage_1_v3.json を直接読む（game から実行: python stages/stage1_v3_design/layout_check.py）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "stage_1_v3.json"), encoding="utf-8") as f:
    raw = json.load(f)

SCALE = 40  # 1文字 = 40px
W = int(raw["world_width"])
P = [(p["id"], p["x"], p["y"], p["w"], p["h"],
      "gate" if p.get("style") == "sealed_gate" else ("wall" if p["id"].startswith("DW") else "solid"))
     for p in raw["platforms"]]
P += [(p["id"], p["x"], p["y"], p["w"], p["h"], "oneway") for p in raw["one_way_platforms"]]
E = [(e["id"], e["x"], e["foot_y"], e["type"]) for e in raw["enemies"]]
cols = W // SCALE + 1


def lane(pred, enemies_pred, label):
    row = [" "] * cols
    for pid, x, y, w, h, k in P:
        if k == "gate":
            for c in range(x // SCALE, (x + w - 1) // SCALE + 1):
                row[c] = "#"
        elif pred(y, k):
            ch = "=" if k == "oneway" else ("|" if k == "wall" else "-")
            for c in range(x // SCALE, (x + w - 1) // SCALE + 1):
                if row[c] == " ":
                    row[c] = ch
    for eid, x, fy, t in E:
        if enemies_pred(fy, t):
            row[x // SCALE] = "f" if t == "shadow_flier" else "e"
    return f"{label:6s}" + "".join(row)


print("x(px) " + "".join(str((i * SCALE) // 1000) if i % 25 == 0 else ("|" if i % 5 == 0 else ".")
                         for i in range(cols)))
FLY = "shadow_flier"
print(lane(lambda y, k: k == "oneway", lambda fy, t: t != FLY and fy < 300, "上層"))
print(lane(lambda y, k: False, lambda fy, t: t == FLY, "空中"))
print(lane(lambda y, k: k == "solid" and 300 <= y < 540, lambda fy, t: t != FLY and 300 <= fy <= 540, "中層"))
print(lane(lambda y, k: (k == "solid" and y >= 540) or k == "wall", lambda fy, t: t != FLY and fy > 540, "地下"))
print("凡例: = すり抜け足場  - 固体の床  | 地下の壁  # 城門  e 影這い  f 影翔け")

# 到達チェック（実測: 一段 144px / 二段 288px）
JUMP1, JUMP2 = 144.3, 288.5
links = [("S01", "R1"), ("R1", "U1"), ("B01", "U1"), ("U1", "U2"), ("U2", "U3"), ("U3", "U4"),
         ("PED", "U3"), ("U5", "U6"), ("D1", "ST1"), ("ST1", "ST2"), ("ST2", "G03")]
d = {p[0]: p for p in P}
print()
for a, b in links:
    A, B = d[a], d[b]
    rise = A[2] - B[2]
    gap = max(0, B[1] - (A[1] + A[3]))
    need = "一段" if rise <= JUMP1 - 20 else ("二段" if rise <= JUMP2 - 20 else "不可")
    print(f"{a:5s}->{b:5s} 上昇 {rise:+5.0f}px 水平の隙間 {gap:4.0f}px  -> {need}（余裕 {(JUMP1 if need == '一段' else JUMP2) - rise:4.0f}px）")
print(f"\n地下の天井（中層の下面540）と D1 床({d['D1'][2]})の間 {d['D1'][2] - 540}px / 一段ジャンプ＋身長 {JUMP1 + 40:.0f}px")

# 縦の視認性（カメラ規則: camera.y = 着地した足元y − 0.53×540、範囲 camera_bounds）
OFF, VIEW_H = 0.53 * 540, 540
CAM_TOP, CAM_BOTTOM = raw["camera_bounds"]["top"], raw["camera_bounds"]["bottom"] - VIEW_H
claims = [("G02", "EU1"), ("U1", "E01"), ("D1", "E01"), ("U3", "E02"), ("G03", "EU3"), ("G03", "E03"),
          ("U4", "E03"), ("U4", "EU3"), ("G05", "EU4"), ("U6", "E04"), ("U6", "EU4"), ("G02s", "F1"),
          ("U3", "F2"), ("G04s", "F3")]
ed = {e[0]: e for e in E}
size = {"shadow_crawler": 20, "shadow_flier": 22}
print()
for plat, eid in claims:
    foot = d[plat][2]
    cy = min(max(foot - OFF, CAM_TOP), CAM_BOTTOM)
    fy, t = ed[eid][2], ed[eid][3]
    top, bottom = fy - size[t], fy
    full = cy <= top and bottom <= cy + VIEW_H
    print(f"{plat:4s}に立つ -> {eid}: 画面 y={cy:6.0f}〜{cy + VIEW_H:4.0f} / 体 {top}〜{bottom}  {'全身が見える' if full else '見えない・一部だけ'}")
