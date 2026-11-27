"""v4.0 設計用: 実際の物理コードで「段差ごとの最大飛距離」「落下の時間と横移動」「登攀の速さ」を計測する。

game フォルダから実行する: python stages/stage1_v4_design/motion_probe.py
結果は motion_probe.json にも保存する（地図・見積もりスクリプトが読む）。ゲームのコード・データは変更しない。
"""
import json
import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.getcwd())
import pygame  # noqa: E402

pygame.init()
import config  # noqa: E402
from stages import parse_stage  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import World  # noqa: E402

DT = config.FIXED_DT
OUT = Path(__file__).with_name("motion_probe.json")


def flat_world(width=20000, ground_y=1300, ledge=None):
    """平地（ledge=(x, y) を与えると x より右は ground_y の高さ、左は y の高さの崖）。"""
    plats = [{"id": "G", "x": 0, "y": ground_y, "w": width, "h": 100}]
    if ledge:
        lx, ly = ledge
        plats = [{"id": "L", "x": 0, "y": ly, "w": lx, "h": ground_y - ly},
                 {"id": "G", "x": lx, "y": ground_y, "w": width - lx, "h": 100}]
    raw = {"spawn": {"x": 200, "y": (ledge[1] if ledge else ground_y) - 40}, "goal_x": width - 100,
           "world_width": width, "wall": {"start_x": -99999, "speed": 0}, "kill_y": 5000,
           "camera_bounds": {"top": -2000, "bottom": 4000}, "platforms": plats}
    return parse_stage(raw)


def step(w, inp):
    if w.update(DT, inp):
        inp.clear_edges()


def trajectory(double=False, dash=False):
    """高さ 1000 の崖の縁まで右へ助走して跳ぶ（下降側も記録できる）。頂点で二段目、二段目の頂点で空中ダッシュ。
    [(t, dx, rise)] を返す（rise は + が上。崖の下まで落ちる）。"""
    w = World(flat_world(ledge=(600, 300)), with_graphics=False)
    inp = InputState()
    p = w.player
    inp.simulate_press("right")
    while p.rect.right < 598:
        step(w, inp)
    x0, y0 = p.rect.x, p.rect.bottom
    inp.simulate_press("jump")
    step(w, inp)
    pts, t, did2, didd = [(0.0, 0.0, 0.0)], DT, False, False
    pts.append((t, p.rect.x - x0, y0 - p.rect.bottom))
    while t < 4:
        if double and not did2 and p.vy >= -30:
            inp.simulate_release("jump"); inp.simulate_press("jump"); did2 = True
        if dash and did2 and not didd and p.vy >= 0:
            inp.simulate_press("dash"); didd = True
        step(w, inp)
        if didd:
            inp.simulate_release("dash")
        t += DT
        pts.append((round(t, 4), round(p.rect.x - x0, 2), round(y0 - p.rect.bottom, 2)))
        if p.on_ground and t > 0.1:
            break
    return pts


def reach(pts, h):
    """段差 h（+ が上）の上面に着地できる最大の水平距離と、そのときの所要時間（下降中に高さ h を通る点）。"""
    best = None
    for (t0, x0, r0), (t1, x1, r1) in zip(pts, pts[1:]):
        if r0 >= h > r1:   # 下降中に高さ h を通過
            k = (r0 - h) / (r0 - r1)
            best = (round(x0 + (x1 - x0) * k, 1), round(t0 + (t1 - t0) * k, 3))
    return best


def fall(drop, steer=True):
    """崖から走って落ちる。落差 drop を落ちる時間と横移動量（右を押し続ける）。"""
    w = World(flat_world(ground_y=1300, ledge=(600, 1300 - drop)), with_graphics=False)
    inp = InputState()
    p = w.player
    inp.simulate_press("right")
    t, left_at = 0.0, None
    while t < 6:
        step(w, inp)
        t += DT
        if left_at is None and p.rect.left > 600:
            left_at, x_at = t, p.rect.x
        if left_at is not None and p.on_ground:
            return {"drop": drop, "time": round(t - left_at, 3), "dx": round(p.rect.x - x_at, 1),
                    "vy_land": None}
    return None


def main():
    single, double, dash = trajectory(), trajectory(double=True), trajectory(double=True, dash=True)
    res = {"run_speed": config.PROTAGONIST["stats"]["move_speed"],
           "wall_speed_default": config.WALL_DEFAULTS["speed"],
           "single_apex": max(r for _, _, r in single), "double_apex": max(r for _, _, r in double),
           "reach": {}, "fall": []}
    print(f"一段の頂点 {res['single_apex']:.1f}px / 二段の頂点 {res['double_apex']:.1f}px")
    res["traj"] = {"single": single, "double": double, "double_dash": dash}
    print("段差 h | 一段: 最大飛距離, 時間 | 二段: 最大飛距離, 時間 | 二段+空中ダッシュ")
    for h in (-600, -400, -200, -96, 0, 32, 64, 96, 124, 160, 200, 240, 268):
        a, b, c = reach(single, h), reach(double, h), reach(dash, h)
        res["reach"][h] = {"single": a, "double": b, "double_dash": c}
        print(f"{h:+5d}  | {a} | {b} | {c}")
    for d in (128, 256, 400, 600, 800, 1000):
        f = fall(d)
        res["fall"].append(f)
        print(f"落下 {d:5d}px: {f['time']:.2f}秒, 横 {f['dx']:.0f}px")
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT.name)


if __name__ == "__main__":
    main()
