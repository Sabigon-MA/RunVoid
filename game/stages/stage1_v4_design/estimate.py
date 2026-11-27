"""ルートごとの所要時間の見積もりと、追跡壁の4方式（A〜D）の比較。

所要時間は、motion_probe.json（実際の物理で計測した跳躍・落下の時間）と、走る速さ 336px/s から
区間ごとに積み上げた**見積もり**。実装後はボットの実測で置き換える（テスト計画 T-07）。

ペース:
  標準  … 迷わずに進む（必須テレポートの判断 0.6 秒、各跳躍の着地後 0.1 秒）
  初見  … 移動の時間 ×1.35、テレポートの判断 1.5 秒、各エリアの入口で 1.0 秒見回す

game フォルダから実行する: python stages/stage1_v4_design/estimate.py
結果は estimate_result.json に保存する（地図・資料の数値はここから取る）。
"""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v4data as D  # noqa: E402

PROBE = json.loads((HERE / "motion_probe.json").read_text(encoding="utf-8"))
RUN = PROBE["run_speed"]
COOLDOWN = 2.0

PACES = {
    "標準": {"move": 1.0, "think": 0.6, "land": 0.1, "look": 0.0},
    "2回目": {"move": 1.15, "think": 1.0, "land": 0.12, "look": 0.5},
    "初見": {"move": 1.35, "think": 1.5, "land": 0.15, "look": 1.0},
}
TUNE_PACE = "2回目"     # C・D の壁の速さを合わせるペース（設計判断。資料 §6 を参照）


def _interp(table, h):
    ks = sorted(table)
    if h <= ks[0]:
        return table[ks[0]]
    if h >= ks[-1]:
        return table[ks[-1]]
    i = bisect.bisect_left(ks, h)
    a, b = ks[i - 1], ks[i]
    return table[a] + (table[b] - table[a]) * (h - a) / (b - a)


def jump_time(kind, rise):
    """段差 rise（+ が上）に着地するまでの時間（motion_probe の実測から補間）。"""
    key = {"j1": "single", "j2": "double", "j2d": "double_dash"}[kind]
    tab = {int(h): v[key][1] for h, v in PROBE["reach"].items() if v[key]}
    return _interp(tab, rise)


def fall_time(drop):
    tab = {f["drop"]: f["time"] for f in PROBE["fall"]}
    tab[0] = 0.0
    return _interp(tab, drop)


# ルート: (操作, x, 足元 y, メモ)。操作 run / j1 / j2 / j2d / drop / tp:<敵>（判断してから交換）/ fall（交換後に落ちる）
# 必須の交換には "!" を付ける（tp!:EA）
R_UP = [  # 上層ルート（屋根 → 水道橋 → 鐘楼の上 → 浮島 → 橋 → 城壁の上）
    ("run", 300, 760), ("j1", 600, 664), ("j1", 720, 568), ("j2", 1060, 400, "崩れた足場 U1"),
    ("j1", 1260, 360, "見張り塔"), ("j1", 1500, 480, "屋根1"), ("j1", 1760, 500), ("j1", 2020, 470),
    ("j1", 2280, 520), ("j1", 2560, 480), ("j1", 2840, 460), ("run", 3400, 460, "水道橋"),
    ("j2", 3920, 460, "水道橋の崩落を二段で"), ("run", 4700, 460, "高窓の回廊"), ("j1", 4900, 500),
    ("j1", 5340, 530, "鐘楼の段2"), ("tp!:EA", 5780, 300, "GATE1"),
    ("run", 5900, 300), ("j1", 6100, 340), ("j1", 6440, 280), ("run", 6540, 280),
    ("tp!:F05", 6900, 240, "GATE2"), ("fall", 6900, 340), ("run", 7660, 340, "橋"),
    ("j2", 8060, 360, "橋の隙間を二段で"), ("j1", 8420, 340, "東の崖の上"), ("run", 8980, 340),
    ("tp!:E15", 9180, 340, "GATE3"), ("run", 9480, 340), ("j1", 9560, 240, "城壁の塔"), ("j1", 9720, 400),
    ("run", 9780, 400), ("tp!:E17", 9960, 560, "GATE4"), ("run", D.GOAL_X, 560),
]
R_MID = [  # 中層ルート（通り → 崩落を二段で → 地下水路 → 階段 → 身廊 → 鐘楼の段1 → 筏 → 断層の底 → 崖 → 中庭）
    ("run", 300, 760), ("j1", 600, 664), ("j1", 720, 568), ("j1", 1060, 600, "堀を越える"),
    ("run", 1440, 600), ("drop", 1520, 760, "通りへ"), ("run", 1700, 760), ("j1", 1760, 660, "瓦礫"),
    ("drop", 1880, 760), ("run", 1980, 760), ("j1", 2180, 680, "陥没を越えて瓦礫へ"), ("j1", 2260, 600),
    ("run", 2370, 600), ("drop", 2440, 760), ("run", 2620, 760), ("j2", 3020, 760, "崩落を二段で（CP1）"),
    ("run", 3340, 760), ("drop", 3620, 1240, "地下水路へ"), ("run", 3700, 1240), ("j1", 3930, 1120, "水路を越えて階段へ"),
    ("j1", 3990, 1000), ("j1", 4050, 880), ("j1", 4110, 760), ("run", 5110, 760, "身廊"),
    ("j1", 5170, 640, "鐘楼の段1"), ("tp!:FB", 5790, 460, "GATE1"), ("fall", 5790, 620),
    ("run", 5880, 620), ("j1", 6040, 700), ("j1", 6320, 680), ("j1", 6560, 640), ("run", 6620, 640),
    ("tp!:E13", 6830, 700, "GATE2"), ("run", 7380, 700), ("drop", 7480, 860, "断層へ"), ("drop", 7660, 1000),
    ("drop", 7840, 1140), ("drop", 7960, 1300, "断層の底"), ("run", 8140, 1300), ("j1", 8280, 1180, "裂け目を越えて段1"),
    ("j1", 8360, 1060, "段2"), ("tp!:F08", 8330, 815, "崖の交換①"), ("j1", 8200, 740, "岩棚M"),
    ("tp!:F09", 8200, 505, "崖の交換②（クールダウン待ち）"), ("j1", 8320, 420, "岩棚N"), ("j1", 8440, 340, "崖の上（CP3）"),
    ("run", 8980, 340), ("tp!:F10", 9160, 560, "GATE3"), ("fall", 9160, 760), ("run", 9240, 760),
    ("j1", 9400, 760, "堀を越える"), ("run", 9600, 760), ("j1", 9640, 660), ("j1", 9720, 560), ("run", 9780, 560),
    ("tp!:E17", 9960, 560, "GATE4"), ("run", D.GOAL_X, 560),
]
# 地下ルート: 中層ルートの A02〜A03 を「陥没 → 地下室 → 地下水路」に置き換える
_i0 = next(i for i, l in enumerate(R_MID) if l[1] == 1980)
_i1 = next(i for i, l in enumerate(R_MID) if l[1] == 3700)
R_LOW = R_MID[:_i0] + [
    ("run", 1990, 760), ("drop", 2060, 1100, "陥没から地下室へ"), ("run", 2860, 1100, "地下室（E07）"),
    ("drop", 2940, 1240, "地下水路へ"), ("run", 3700, 1240),
] + R_MID[_i1 + 1:]
# 熟練: 上層ルートで、任意の交換と空中ダッシュを使う
R_EXP = [
    ("run", 300, 760), ("j1", 600, 664), ("j1", 720, 568), ("j1", 1060, 600), ("run", 1180, 600),
    ("tp:E02", 1280, 360, "見張り塔へ交換"), ("j1", 1500, 480), ("j1", 1760, 500), ("j1", 2020, 470),
    ("j1", 2280, 520), ("j1", 2560, 480), ("j1", 2840, 460), ("run", 3380, 460),
    ("tp:F02", 3720, 440, "水道橋の崩落を交換で"), ("j1", 3920, 460), ("run", 4700, 460), ("j1", 4900, 500),
    ("j1", 5340, 530), ("tp!:EA", 5780, 300), ("run", 5900, 300), ("j1", 6100, 340), ("j1", 6440, 280),
    ("run", 6540, 280), ("tp!:F05", 6900, 240), ("fall", 6900, 340), ("run", 7660, 340),
    ("j2d", 8320, 420, "橋の隙間を二段＋空中ダッシュで岩棚Nへ"), ("j1", 8440, 340), ("run", 8980, 340),
    ("tp!:E15", 9180, 340), ("run", 9480, 340), ("j1", 9560, 240), ("j1", 9720, 400), ("run", 9780, 400),
    ("tp!:E17", 9960, 560), ("run", D.GOAL_X, 560),
]
ROUTES = {"上層": R_UP, "中層": R_MID, "地下": R_LOW, "熟練": R_EXP}


def area_of(x):
    for a, x0, x1, *_ in D.AREAS:
        if x0 <= x < x1:
            return a
    return D.AREAS[-1][0]


def timeline(route, pace):
    """[(t, x, y, 操作, メモ)] を返す。t は各点に着いた時刻。"""
    pc = PACES[pace]
    x, y = D.SPAWN
    t, last_tp = 0.0, -99.0
    out = [(0.0, x, y, "start", "")]
    seen = {"A01"}
    for leg in route:
        op, nx, ny = leg[:3]
        memo = leg[3] if len(leg) > 3 else ""
        a = area_of(nx)
        if a not in seen:
            seen.add(a)
            t += pc["look"]
        dx = abs(nx - x)
        if op == "run":
            dt = dx / RUN * pc["move"]
        elif op in ("j1", "j2", "j2d"):
            dt = max(jump_time(op, y - ny), dx / RUN) * pc["move"] + pc["land"]
        elif op in ("drop", "fall"):
            dt = max(fall_time(max(0.0, ny - y)), dx / RUN) * pc["move"] + pc["land"]
        elif op.startswith("tp"):
            ready = last_tp + COOLDOWN
            dt = max(pc["think"], ready - t)
            last_tp = t + dt
        else:
            raise ValueError(op)
        t += dt
        x, y = nx, ny
        out.append((round(t, 3), nx, ny, op, memo))
    return out


def cross_time(tl, X):
    """主人公が初めて x=X を越える時刻（区間の中で直線に補間。テレポートはその区間の終わりに越える）。"""
    if X <= tl[0][1]:
        return 0.0
    for (t0, x0, *_), (t1, x1, _y, op, _m) in zip(tl, tl[1:]):
        if x0 < X <= x1:
            if op.startswith("tp") or x1 == x0:
                return t1
            return t0 + (t1 - t0) * (X - x0) / (x1 - x0)
    return tl[-1][0]


# ---------------- 追跡壁の方式 ----------------
START_X = -600.0
GAP_MIN = 300.0        # これより近づいたら「危険」（1秒分）
# C・D の区間ごとの速さ（壁の先端がそのエリアにある間の速さ、px/s）。tune() で決める
INTRO_AREAS = ("A01", "A02")   # 導入の区間は初見のペースに合わせる


def tune(target_ratio=0.92, routes=("中層", "地下"), pace=TUNE_PACE):
    """指定ルート・ペースのうち、各エリアで最も時間のかかるルートの平均の横の速さ × target_ratio を、
    そのエリアでの壁の速さにする（＝そのペースの遅いルートでも、エリアを通過する間に壁との距離がほとんど縮まない）。
    導入の区間（INTRO_AREAS）は初見のペースに合わせる。"""
    speeds = {}
    for a, x0, x1, *_ in D.AREAS:
        worst = 0.0
        for name in routes:
            tl = timeline(ROUTES[name], "初見" if a in INTRO_AREAS else pace)
            worst = max(worst, cross_time(tl, min(x1, D.GOAL_X)) - cross_time(tl, x0))
        speeds[a] = round(min(300.0, (x1 - x0) / max(0.1, worst) * target_ratio), 0)
    return speeds


# 距離の上限（D の補助案）: 横の壁との距離が CATCHUP_GAP を超えている間は、超えた分に比例して速くなる（上限 CATCHUP_MAX）
CATCHUP_GAP = 1100.0
CATCHUP_GAIN = 1.0        # 超えた 1px あたり +1px/s
CATCHUP_MAX = 600.0

# B・D の縦の区間。横の壁の先端が x0 に着いたとき、主人公が区間の中（x < x1）にいれば、横の壁はそこで止まり、
# 区間の中だけを下から「侵食の潮」が speed px/s でせり上がる（floor から top まで）。
# 主人公が区間を出る（x ≥ x1）と潮は止まり、横の壁は x0 から再び進む（区間で止まった時間を先行の余裕として与えない）。
# 潮が top に達すると区間全体が飲み込まれる（区間に残っていれば死亡）。主人公がすでに区間の先にいれば潮は起きない
VZONES = [
    {"id": "Z1", "name": "大聖堂の鐘楼", "x0": 5100, "x1": 5600, "floor": 820, "top": 190, "speed": 70.0},
    {"id": "Z2", "name": "大断層の東の崖", "x0": 7900, "x1": 8400, "floor": 1400, "top": 340, "speed": 95.0},
]

SCHEMES = {
    "A": {"label": "常に右へ 300px/s", "per_area": False, "zones": False, "catchup": False},
    "B": {"label": "区間で向きを変える（速さは 300px/s のまま）", "per_area": False, "zones": True, "catchup": False},
    "C": {"label": "区間で速さを変える", "per_area": True, "zones": False, "catchup": False},
    "D": {"label": "B と C の併用", "per_area": True, "zones": True, "catchup": False},
    "D+": {"label": "D ＋ 距離の上限（離れすぎると速くなる）", "per_area": True, "zones": True, "catchup": True},
}


def player_at(tl, t):
    """時刻 t の主人公の足元 (x, y, その区間のメモ)。テレポートの区間は、終わるまで元の位置にいる。"""
    for (t0, x0, y0, *_), (t1, x1, y1, op, memo) in zip(tl, tl[1:]):
        if t <= t1:
            if op.startswith("tp"):
                return (x0, y0, memo) if t < t1 else (x1, y1, memo)
            k = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, memo
    return tl[-1][1], tl[-1][2], ""


def simulate(route, pace, scheme, speeds, dt=0.02, cp=None, wall_gap=None):
    """cp=(チェックポイントの x) を与えると、主人公がそこを越えた時点から、壁を x − wall_gap に置いて始める
    （チェックポイントからの再開の近似。縦の区間はすでに越えたものは飛ばす）。"""
    sc = SCHEMES[scheme]
    tl = timeline(route, pace)
    x, zone, zi, tide = START_X, None, 0, None
    rows, dead, worst = [], None, (1e9, None)
    t = 0.0
    if cp is not None:
        t = cross_time(tl, cp)
        x = cp - wall_gap
        zi = sum(1 for z in VZONES if z["x0"] < x)
    while t <= tl[-1][0]:
        px, py, memo = player_at(tl, t)
        left = px - 12
        if zone is not None:
            tide -= zone["speed"] * dt
            v = zone["speed"]
            if left < x:
                g, kind = left - x, "横"
            elif zone["x0"] <= px < zone["x1"]:
                g, kind = tide - py, "縦"
            else:
                g, kind = left - x, "横（停止中）"
            if px >= zone["x1"] or tide <= zone["top"]:
                if tide <= zone["top"] and zone["x0"] <= px < zone["x1"]:
                    g, kind = -1, "縦"      # 区間が飲み込まれた
                zone, tide = None, None
                zi += 1
        else:
            v = speeds[area_of(max(0.0, x))] if sc["per_area"] else 300.0
            if sc["catchup"] and left - x > CATCHUP_GAP:
                v = min(CATCHUP_MAX, v + (left - x - CATCHUP_GAP) * CATCHUP_GAIN)
            x += v * dt
            if sc["zones"] and zi < len(VZONES) and x >= VZONES[zi]["x0"]:
                if px < VZONES[zi]["x1"]:
                    zone = VZONES[zi]
                    x, tide = zone["x0"], zone["floor"]
                else:
                    zi += 1                 # 主人公はすでに区間の先にいる → 潮は起きない
            g, kind = left - x, "横"
        rows.append((round(t, 2), round(px), round(py), round(x), None if tide is None else round(tide), round(g), kind,
                     round(v, 1)))
        if g < worst[0]:
            worst = (g, (round(t, 2), round(px), round(py), kind, area_of(px), memo))
        if g <= 0 and dead is None:
            dead = (round(t, 2), round(px), round(py), kind, area_of(px), memo)
            break
        t += dt
    area_min = {}
    for r in rows:
        a = area_of(r[1])
        if "停止" in r[6]:
            continue
        area_min[a] = min(area_min.get(a, 1e9), r[5])
    # 必須の交換の地点に着いた時点で、その場で立ち止まって考えられる秒数（壁との距離 ÷ そのときの壁の速さ）
    think = []
    for (t0, *_), (t1, x1, y1, op, memo) in zip(tl, tl[1:]):
        if op.startswith("tp!") and rows:
            r = min(rows, key=lambda r: abs(r[0] - t0))
            if r[0] <= t0 + 0.05:
                think.append({"target": op.split(":")[1], "memo": memo, "t": round(t0, 2), "gap": r[5],
                              "kind": r[6], "seconds": round(r[5] / max(1.0, r[7]), 2)})
    horiz = [r for r in rows if r[6] == "横"]
    return {"clear_time": tl[-1][0], "min_gap": round(worst[0]), "min_at": worst[1], "dead": dead,
            "area_min": area_min, "think": think,
            "max_gap": max((r[5] for r in horiz), default=None),
            "near_share": round(sum(1 for r in horiz if r[5] <= 600) / max(1, len(rows)), 3),
            "rows": rows[::10], "rows_all": rows}


def checkpoint_gaps(scheme, speeds, pace="初見", margin=300, routes=("上層", "中層", "地下")):
    """各チェックポイントについて、再開したときに次のチェックポイント（最後はゴール）まで、どのルートでも
    壁との距離が margin 以上を保てる最小の wall_gap を 50px 刻みで探す。"""
    out = {}
    cps = D.CHECKPOINTS
    for i, (cid, cx, _sp, _n) in enumerate(cps):
        nxt = cps[i + 1][1] if i + 1 < len(cps) else D.GOAL_X
        for gap in range(300, 3001, 50):
            ok = True
            for name in routes:
                ev = simulate(ROUTES[name], pace, scheme, speeds, cp=cx, wall_gap=gap)
                seg = [r for r in ev["rows_all"] if cx <= r[1] < nxt and "停止" not in r[6]]
                if ev["dead"] and ev["dead"][1] < nxt or any(r[5] < margin for r in seg):
                    ok = False
                    break
            if ok:
                out[cid] = gap
                break
        else:
            out[cid] = None
    return out


def main():
    speeds = tune()
    res = {"speeds_C": speeds, "vzones": VZONES, "schemes": SCHEMES, "catchup": [CATCHUP_GAP, CATCHUP_GAIN, CATCHUP_MAX],
           "routes": {}, "eval": {}}
    print("C・D の壁の速さ（エリアごと, px/s）:", speeds)
    for name, r in ROUTES.items():
        for pace in PACES:
            tl = timeline(r, pace)
            res["routes"][f"{name}/{pace}"] = tl
            tps = [l for l in r if l[0].startswith("tp")]
            print(f"{name}/{pace}: クリア {tl[-1][0]:.1f} 秒、交換 {len(tps)} 回（必須 {sum('!' in l[0] for l in tps)}）")
    for scheme in SCHEMES:
        for name, r in ROUTES.items():
            for pace in PACES:
                ev = simulate(r, pace, scheme, speeds)
                res["eval"][f"{scheme}/{name}/{pace}"] = ev
                state = f"死亡 {ev['dead']}" if ev["dead"] else f"最小 {ev['min_gap']}px @ {ev['min_at']}"
                th = " ".join(f"{k['target']}:{k['seconds']}s" for k in ev["think"])
                print(f"[{scheme}] {name}/{pace}: {state} 最大 {ev['max_gap']} 近い割合 {ev['near_share']} 考える {th}")
                ev.pop("rows_all")
    res["checkpoint_gaps"] = {s: checkpoint_gaps(s, speeds) for s in ("C", "D", "D+")}
    print("チェックポイントの wall_gap（初見で次の区切りまで 300px 以上）:", res["checkpoint_gaps"])
    (HERE / "estimate_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()


