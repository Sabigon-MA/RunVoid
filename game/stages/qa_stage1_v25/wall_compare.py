"""追跡壁の開始位置 -600 / -450 の比較（実際の stage_1.json・tests/stage1_bot.py・実際のクリック経路）。
使い方: python wall_compare.py <game_dir>   → 標準出力と wall_compare.json
"""
import json, os, sys
GAME = sys.argv[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests"))
os.chdir(GAME)
import test_gameplay  # noqa  (SDL dummy)
from test_gameplay import STAGE_1
import stage1_bot as bot

SPEED = STAGE_1.wall.speed


def play(ws, **kw):
    return bot.play(STAGE_1, wall_start=ws, **kw)


FAILS_BELOW_MAX = []


def max_delay(ws, key, step=0.05, hi=6.0, **kw):
    """key の待ち時間を 0〜hi で全部試し、クリアできる最大値。それより短い待ちで失敗したものは記録する。"""
    ok = {}
    d = 0.0
    while d <= hi + 1e-9:
        ok[d] = play(ws, **{key: d}, **kw).state == "clear"
        d = round(d + step, 4)
    best = max((d for d, v in ok.items() if v), default=None)
    holes = [d for d, v in ok.items() if not v and best is not None and d < best]
    if holes:
        FAILS_BELOW_MAX.append((ws, key, kw, holes))
    return best


def first_wall_on_screen(ws, **kw):
    r = play(ws, record=True, **kw)
    for i, row in enumerate(r.rows):
        if row[4] > row[5]:            # 壁の先端 > カメラ左端
            return round((i + 1) * bot.DT, 2)
    return None


out = {}
for ws in (-600.0, -450.0):
    d = {}
    d["start_gap"] = STAGE_1.spawn[0] - ws
    d["idle_until_wall_visible"] = round((0 - ws) / SPEED, 2)      # 動かずにいると壁が画面左端に現れるまで
    for dash in (False, True):
        k = "dash" if dash else "nodash"
        r = play(ws, policy="required", dash=dash)
        d[f"{k}_required"] = dict(state=r.state, t=round(r.world.elapsed, 2), min_gap=round(r.min_gap),
                                  arrive={g: (round(a[0], 2), round(a[1])) for g, a in r.arrive.items()},
                                  slack_gate1=round(r.arrive["GATE1"][1] / SPEED, 2))
        d[f"{k}_max_gate1"] = max_delay(ws, "gate_delay", policy="required", dash=dash, gate2_delay=0.0)
        d[f"{k}_max_gate2"] = max_delay(ws, "gate2_delay", policy="required", dash=dash, gate_delay=0.0)
        for g1 in (1.0, 2.0):
            d[f"{k}_max_gate2_after_g1_{g1}"] = max_delay(ws, "gate2_delay", policy="required", dash=dash, gate_delay=g1)
        # 開始時のためらい: 開始位置で h 秒止まる = 壁が 300h 近い所から始まるのと同じ（敵は画面外で停止中）
        hs = [round(i * 0.05, 2) for i in range(0, 81)]
        okh = [h for h in hs if play(ws + SPEED * h, policy="required", dash=dash, gate_delay=1.0).state == "clear"]
        lo = max(okh, default=None)
        holes = [h for h in hs if h not in okh and lo is not None and h < lo]
        if holes:
            FAILS_BELOW_MAX.append((ws, "start_hesitation", dash, holes))
        d[f"{k}_max_start_hesitation_with_gate1_1s"] = lo
        # 誤クリック: ゲート1で先に後ろの E02 と交換してしまう
        wr = play(ws, policy="required", dash=dash, wrong_first={"GATE1": "E02"})
        d[f"{k}_misclick_e02"] = dict(state=wr.state, cause=wr.world.death_cause,
                                      swaps=[s.target for s in wr.swaps], t=round(wr.world.elapsed, 2),
                                      min_gap=round(wr.min_gap), hp=wr.world.player.hp)
        d[f"{k}_misclick_e02_max_gate1_delay"] = max_delay(ws, "gate_delay", policy="required", dash=dash,
                                                           wrong_first={"GATE1": "E02"})
        # 踏み切り位置のばらつき ±20px × 100 通り、各ゲートで1秒考える
        ok = sum(play(ws, policy="required", dash=dash, jitter=20, seed=s, gate_delay=1.0).state == "clear"
                 for s in range(100))
        d[f"{k}_jitter20_gate1s_clear"] = ok
    d["first_wall_on_screen_nodash_required"] = first_wall_on_screen(ws, policy="required", dash=False)
    d["expert"] = (lambda r: dict(state=r.state, t=round(r.world.elapsed, 2), swaps=[s.target for s in r.swaps],
                                  min_gap=round(r.min_gap)))(play(ws, policy="expert"))
    d["air_e02_nodash"] = (lambda r: dict(state=r.state, t=round(r.world.elapsed, 2),
                                          slack_gate1=round(r.arrive["GATE1"][1] / SPEED, 2)))(
        play(ws, policy="required", dash=False, air_e02=True))
    d["no_teleport"] = (lambda r: dict(state=r.state, cause=r.world.death_cause,
                                       max_right=round(r.world.player.rect.right)))(play(ws, policy="none"))
    out[str(int(ws))] = d
    print(f"### wall_start {ws}")
    for k, v in d.items():
        print(f"  {k}: {v}")

print("最大値より短い待ちでの失敗:", FAILS_BELOW_MAX or "なし")
out["fails_below_max"] = [list(map(str, f)) for f in FAILS_BELOW_MAX]
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wall_compare.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
