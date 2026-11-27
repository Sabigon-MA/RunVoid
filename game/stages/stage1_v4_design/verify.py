"""v4.0 設計案の検証。実際の物理・テレポート・カメラのコードを使う（ゲームのコード・データは変更しない）。

1. 跳躍の検証: 設計した足場のつながり（LINKS）を1本ずつ、実際の操作（右を押す・ジャンプ・二段目・空中ダッシュ）で試す。
   「届かないはず」のつながり（expect=False）は届かないことを確かめる（必須テレポートの抜け道がないか）。
2. テレポートの検証: 立ち位置から交換相手が画面内に見えるか（カメラの縦の規則も実物）、交換が成立するか、
   交換後に予定の足場に着くか。影翔けは巡回・追跡で動くので、待ち時間を変えて4回試す。
3. 見えないはずの組み合わせ（NOVIS）: 必須テレポートの相手が、登らずに見えてしまわないか。
4. 敵の足場: 影這いが足場の上に立っているか、影翔けが地形に埋まっていないか。

game フォルダから実行する: python stages/stage1_v4_design/verify.py
結果は verify_result.json に保存する。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.getcwd())
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pygame  # noqa: E402

pygame.init()
import config  # noqa: E402
from stages import parse_stage  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.targeting import find_target, is_targetable  # noqa: E402
from systems.world import PLAYING, World  # noqa: E402

import v4data as D  # noqa: E402
from build_draft import draft_dict  # noqa: E402

DT = config.FIXED_DT
T = {t["id"]: t for t in D.TERRAIN}
NO_WALL = {"start_x": -1e6, "speed": 0, "thickness": 32}

# (from, to, 操作, オプション)。操作: j1=一段 / j2=二段 / j2d=二段+空中ダッシュ / drop=歩いて落ちる
# start: 立ち位置の x（省略時は from の端から 50px 手前）、dir: +1 右 / -1 左 / 0 その場で真上
# also: 予定の足場以外に着いてもよい足場（近道になるだけのもの）、expect=False: 届いてはいけない
LINKS = [
    # A01
    ("A1S1", "A1G2", "j1", {}), ("A1G2", "A1G3", "j1", {}), ("A1G3", "A1G4", "j1", {}),
    ("A1G3", "A1U1", "j2", {}), ("A1U1", "A1T", "j1", {}), ("A1G4", "A1T", "j2", {"start": 1180}),
    ("A1M0", "A1M1", "j1", {"start": 920}), ("A1M1", "A1G4", "j2", {"start": 1000}),
    ("A1G4", "A2ST1", "drop", {}),
    # A02
    ("A1T", "A2R1", "j1", {}), ("A2R1", "A2R2", "j1", {}), ("A2R2", "A2R3", "j1", {}),
    ("A2R3", "A2R4", "j1", {}), ("A2R4", "A2R5", "j1", {}), ("A2R5", "A2R6", "j1", {}),
    ("A2ST1", "A2P1", "j1", {"start": 1640}), ("A2P1", "A2R2", "j2", {"start": 1780, "dir": 0}),
    ("A2ST1", "A2P2", "j1", {}), ("A2ST2", "A2P2", "j1", {"start": 2130, "dir": 1}), ("A2P2", "A2H1", "j1", {}),
    ("A2H1", "A2R4", "j1", {"start": 2310, "dir": 0}), ("A2H1", "A2ST2", "drop", {}),
    ("A2ST2", "A3S1", "j2", {}), ("A2ST1", "A2C", "drop", {}), ("A2C", "A3C1", "drop", {}),
    # A03
    ("A3AQ1", "A3AQ2", "j2", {}), ("A3S1", "A3C1", "drop", {}), ("A3C1", "A3C2", "j1", {"also": ["A3K1"]}),
    ("A3C2", "A3K1", "j1", {"start": 3850, "dir": 1}), ("A3K1", "A3K2", "j1", {}), ("A3K2", "A3K3", "j1", {}),
    ("A3K3", "A3S2", "j1", {}),
    # A04
    ("A4CL", "A4C2", "j1", {}), ("A4N", "A4C1", "j2", {"start": 4720, "dir": 0}), ("A4C1", "A4C2", "j1", {}),
    ("A4C2", "A4L2", "j1", {}), ("A4N", "A4L1", "j1", {"start": 5080}), ("A4L1", "A4L2", "j1", {}),
    ("A4L2", "A4L3", "j1", {}), ("A4L3", "A4L4", "j1", {"dir": -1}), ("A4L4", "A4L5", "j1", {}),
    # A05
    ("A5I1", "A5I2", "j1", {}), ("A5I2", "A5I3", "j1", {}), ("A5L0", "A5R1", "j1", {}),
    ("A5R1", "A5R2", "j1", {}), ("A5R2", "A5R3", "j1", {}), ("A5I1", "A5R1", "drop", {}),
    ("A5I2", "A5R2", "drop", {}),
    # A06
    ("A6B1", "A6BF", "j2", {}), ("A6B1", "A6EC", "j2d", {"also": ["A6N"]}), ("A6BF", "A6EC", "j1", {}),
    ("A6B1", "A6BF", "j1", {"expect": False}),
    ("A5R4", "A6D1", "drop", {}), ("A6D1", "A6D2", "drop", {}), ("A6D2", "A6D3", "drop", {}),
    ("A6D3", "A6F1", "drop", {}), ("A6F1", "A6K1", "j1", {}), ("A6K1", "A6K2", "j1", {}),
    ("A6N", "A6EC", "j1", {"start": 8340}),
    # A07
    ("A7RW", "A7RT", "j1", {}), ("A7RT", "A7RW2", "j1", {}), ("A7BY1", "A7BY2", "j1", {}),
    ("A7BY2", "A7ST1", "j1", {"start": 9580}), ("A7ST1", "A7ST2", "j1", {}),
    # 届かないはず（必須テレポートの抜け道がないこと）
    ("A6K2", "A6M", "j2", {"start": 8370, "dir": -1, "expect": False}),
    ("A6K1", "A6M", "j2", {"start": 8300, "dir": -1, "expect": False}),
    ("A6M", "A6N", "j2", {"start": 8200, "dir": 1, "expect": False}),
    ("A4L5", "A5I1", "j2d", {"expect": False}),
    ("A5I3", "A5I4", "j2d", {"expect": False}),
    ("A6EC", "A7RW", "j2d", {"expect": False}),
    ("A7RW2", "A7KC", "j2d", {"expect": False}),
]

# (立つ足場, 立ち位置 x, 交換相手, 交換後の操作, 着く足場, 必須か)
SWAPS = [
    ("A1G3", 860, "E01", None, "A1G4", False),
    ("A1G4", 1180, "E02", None, "A1T", False),
    ("A2ST2", 2200, "E04", None, "A2R4", False),
    ("A2R4", 2400, "E05", None, "A2ST2", False),
    ("A2ST2", 2620, "F01", ("j1", 1), "A3S1", False),
    ("A3AQ1", 3380, "F02", ("j1", 1), "A3AQ2", False),
    ("A4L2", 5420, "EA", None, "A5I1", True),
    ("A4L5", 5560, "EA", None, "A5I1", True),
    ("A4L1", 5240, "FB", None, "A5L0", True),
    ("A5I3", 6540, "F05", None, "A5I4", True),
    ("A5R3", 6620, "E13", None, "A5R4", True),
    ("A6B1", 7640, "F07", ("j1", 1), "A6BF", False),
    ("A6K2", 8370, "F08", ("j1", -1), "A6M", True),
    ("A6M", 8185, "F09", ("j1", 1), "A6N", True),
    ("A6EC", 8980, "E15", None, "A7RW", True),
    ("A6EC", 8980, "F10", None, "A7BY1", True),
    ("A7RW2", 9780, "E17", None, "A7KC", True),
    ("A7ST2", 9780, "E17", None, "A7KC", True),
]

# (立つ足場, 立ち位置 x, 見えてはいけない相手, 理由)
NOVIS = [
    ("A4N", 5560, "EA", "鐘楼を登らずに GATE1 を越えられない"),
    ("A4N", 5560, "FB", "同上"),
    ("A4C2", 5000, "EA", "シャンデリアから直接は交換できない（鐘楼に入る必要がある）"),
    ("A3S2", 4300, "F04", "（参考）前庭から F04 は見えない"),
    ("A5I3", 6540, "E13", "浮島からは下の筏ルートの相手が見えない（層ごとに相手が決まる）"),
    ("A5R3", 6620, "F05", "筏からは上の浮島ルートの相手が見えない"),
    ("A6F1", 8100, "F09", "断層の底から2段目の交換相手は見えない（順に登る必要がある）"),
    ("A6K1", 8300, "F08", "崖の段1からは1段目の交換相手も見えない（段2まで登る必要がある）"),
]

SWAP_DELAYS = (0.3, 0.9, 1.5, 2.4)


def make_world(enemy_ids=()):
    return World(parse_stage(draft_dict(enemy_ids=set(enemy_ids), wall=NO_WALL)), with_graphics=False)


def step(w, inp):
    if w.update(DT, inp):
        inp.clear_edges()


def over_target(rect, b) -> bool:
    """体の中心が目標の足場の上（左右の端から 14px 内側）にあり、足元が上面より上（すり抜け足場は下からでもよい）。"""
    inside = b["x0"] + 14 <= rect.centerx <= b["x1"] - 14
    return inside and (rect.bottom <= b["top"] + 2 or b["kind"] == "oneway")


def click_point(enemy, camera):
    """画面に見えている部分の中で、当たり判定の中心に最も近い点（体の一部だけが見えている場合もクリックできる）。"""
    box = enemy.hurtbox.clip(camera.view_rect)
    cx, cy = enemy.hurtbox.center
    return (min(max(cx, box.left + 1), box.right - 1), min(max(cy, box.top + 1), box.bottom - 1))


def surface_under(rect):
    for t in D.TERRAIN:
        if abs(rect.bottom - t["top"]) < 1.01 and rect.right > t["x0"] and rect.left < t["x1"]:
            return t["id"]
    return None


def place(w, foot_x, foot_y, settle=0.3):
    p = w.player
    p.place_foot(foot_x, foot_y)
    p.vx = p.vy = 0
    w.max_x = p.rect.x
    w.camera.snap_to(p.rect)
    inp = InputState()
    for _ in range(int(settle / DT)):
        step(w, inp)
    return inp


def run_link(frm, to, mode, opt):
    a, b = T[frm], T[to]
    d = opt.get("dir")
    if d is None:
        d = 1 if (b["x0"] + b["x1"]) / 2 > (a["x0"] + a["x1"]) / 2 else -1
    start = opt.get("start", a["x1"] - 50 if d > 0 else a["x0"] + 50 if d < 0 else (a["x0"] + a["x1"]) / 2)
    w = make_world()
    inp = place(w, start, a["top"], 0.1)
    p = w.player
    key = {1: "right", -1: "left"}.get(d)
    if key:
        inp.simulate_press(key)
    jumped = mode == "drop"
    did2 = dashed = False
    air_frames = 0
    released = False
    for _ in range(int(5 / DT)):
        if not jumped and p.on_ground:
            edge = (d > 0 and p.rect.right >= a["x1"] - 2) or (d < 0 and p.rect.left <= a["x0"] + 2)
            blocked = d != 0 and w.terrain.overlaps_solid(p.rect.move(2 * d, 0))
            if edge or blocked or d == 0:
                inp.simulate_press("jump")
                jumped = True
        if jumped and mode in ("j2", "j2d") and not did2 and not p.on_ground and p.vy >= -30:
            inp.simulate_release("jump"); inp.simulate_press("jump"); did2 = True
        elif jumped and mode == "j1" and not p.on_ground and p.vy >= 0:
            inp.simulate_release("jump")   # 頂点を過ぎたら離す（押した直後に離すと低いジャンプになる）
        if mode == "j2d" and did2 and not dashed and p.vy >= 0:
            inp.simulate_press("dash"); dashed = True
        # 目標の真上に来たら方向キーを離す（行き過ぎ防止。人間もそうする）
        if key and not released and not p.on_ground and over_target(p.rect, b):
            inp.simulate_release(key); released = True
        step(w, inp)
        if dashed:
            inp.simulate_release("dash")
        if w.state != PLAYING:
            return {"ok": False, "landed": "DEAD:" + str(w.death_cause)}
        if not p.on_ground:
            air_frames += 1
        elif air_frames > 2:
            got = surface_under(p.rect)
            return {"ok": got in [to] + opt.get("also", []), "landed": got, "x": round(p.rect.centerx)}
    return {"ok": False, "landed": "timeout"}


def run_swap(frm, sx, target, follow, to, delay):
    a = T[frm]
    w = make_world([target])
    inp = place(w, sx, a["top"], delay)
    p = w.player
    enemy = next(e for e in w.enemies if e.enemy_id == target)
    if not is_targetable(enemy, w.camera):
        return {"ok": False, "why": "見えない", "cam_y": round(w.camera.y)}
    pos = w.camera.to_screen(*click_point(enemy, w.camera))
    sel = find_target(w.enemies, w.camera, w.camera.to_world(*pos))
    inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    step(w, inp)
    inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    if sel is None or w.teleport.count != 1:
        why = "カーソルの下にいない" if sel is None else w.teleport.last_result.reason
        return {"ok": False, "why": f"交換不成立（{why}）", "hp": p.hp}
    after = (round(p.rect.centerx), round(p.rect.bottom))
    b = T[to]
    key = None
    if follow:
        mode, d = follow
        key = {1: "right", -1: "left"}[d]
        inp.simulate_press(key)
        inp.simulate_press("jump")
    released = False
    air = 0
    for _ in range(int(4 / DT)):
        if key and not released and not p.on_ground and over_target(p.rect, b):
            inp.simulate_release(key); released = True
        if follow and air > 2 and p.vy >= 0:
            inp.simulate_release("jump")
        step(w, inp)
        if w.state != PLAYING:
            return {"ok": False, "why": "DEAD:" + str(w.death_cause), "after": after}
        if not p.on_ground:
            air += 1
        if p.on_ground and (air > 2 or not follow):
            got = surface_under(p.rect)
            return {"ok": got == to, "landed": got, "after": after, "cam_y": round(w.camera.y)}
    return {"ok": False, "why": "timeout", "after": after}


def visible_from(frm, sx, target, delay=0.6):
    w = make_world([target])
    place(w, sx, T[frm]["top"], delay)
    enemy = next(e for e in w.enemies if e.enemy_id == target)
    return is_targetable(enemy, w.camera), round(w.camera.y)


def check_enemies():
    out = []
    for eid, ty, x, fy, *_ in D.ENEMIES:
        if ty == "shadow_crawler":
            under = [t["id"] for t in D.TERRAIN if abs(t["top"] - fy) < 0.5 and t["x0"] + 18 <= x <= t["x1"] - 18]
            out.append((eid, bool(under), under))
        else:
            body = pygame.FRect(x - 17, fy - 22, 34, 22)
            hit = [t["id"] for t in D.TERRAIN if t["kind"] == "solid"
                   and pygame.FRect(t["x0"], t["top"], t["x1"] - t["x0"], t["bottom"] - t["top"]).colliderect(body)]
            out.append((eid, not hit, hit))
    return out


def main():
    res = {"links": [], "swaps": [], "novis": [], "enemies": []}
    bad = 0
    print("== 跳躍 ==")
    for frm, to, mode, opt in LINKS:
        r = run_link(frm, to, mode, opt)
        expect = opt.get("expect", True)
        good = r["ok"] == expect
        bad += not good
        res["links"].append({"from": frm, "to": to, "mode": mode, "expect": expect, **r, "pass": good})
        print(f"{'OK ' if good else 'NG '} {frm:6s} -> {to:6s} {mode:4s} 期待={'届く' if expect else '届かない'} 結果={r}")
    print("== テレポート ==")
    for frm, sx, tgt, follow, to, req in SWAPS:
        rs = [run_swap(frm, sx, tgt, follow, to, dl) for dl in SWAP_DELAYS]
        # 必須の交換は待ち時間によらず成立すること。任意の交換はすぐに交換した場合（最初の2回）に成立すればよい
        good = all(r["ok"] for r in (rs if req else rs[:2]))
        bad += not good
        res["swaps"].append({"from": frm, "x": sx, "target": tgt, "to": to, "required": req, "pass": good,
                             "runs": rs})
        print(f"{'OK ' if good else 'NG '} {frm:6s}@{sx} <-> {tgt:4s} -> {to:6s} {'必須' if req else '任意'} "
              + " / ".join(str(r) for r in rs))
    print("== 見えてはいけない ==")
    for frm, sx, tgt, why in NOVIS:
        vis = [visible_from(frm, sx, tgt, dl)[0] for dl in SWAP_DELAYS]
        good = not any(vis)
        bad += not good
        res["novis"].append({"from": frm, "x": sx, "target": tgt, "why": why, "pass": good})
        print(f"{'OK ' if good else 'NG '} {frm}@{sx} から {tgt} は見えない: {vis} ({why})")
    print("== 敵の足場 ==")
    for eid, good, info in check_enemies():
        bad += not good
        res["enemies"].append({"id": eid, "pass": good, "info": info})
        if not good:
            print("NG", eid, info)
    print(f"敵 {len(D.ENEMIES)} 体の足場を確認")
    res["fail_count"] = bad
    res["counts"] = {"links": len(LINKS), "swaps": len(SWAPS), "novis": len(NOVIS), "enemies": len(D.ENEMIES)}
    (HERE / "verify_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"不合格 {bad} 件")


if __name__ == "__main__":
    main()
