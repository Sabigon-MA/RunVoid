"""追跡壁 -600 / -450 の再比較（v2.5 修正済みボット基準）。

    cd game
    python stages/qa_stage1_v25/wall_compare_v2.py      → wall_compare_v2.json / wall_compare_v2_output.txt

A. 決定的な測定（ボットの入力は完璧）: wall_compare.py と同じ（修正済みボットで測った wall_compare.json を読む）
B. 判断時間ごとの死亡率: ゲート1で考える時間を 0〜4 秒で振り、ダッシュ有無 × 踏み切り±20px × 照準のずれ σ=8px（外れたら0.3秒後に押し直す）
   の各 10 通りで死亡率を数える（ゲート2では1秒考える）
C. 仮のプレイヤーモデル（モンテカルロ、-600 と -450 で同じ乱数を使う対の比較）:
   ダッシュ使用 50% / 踏み切り±20px / 開始時のためらい 0〜1.0秒 / ゲート1で考える 0〜4.0秒 / ゲート2で考える 0〜3.0秒 /
   ゲート1で誤って E02 と交換 15% / 区間3で E02 と空中交換 30% / 照準のずれ σ=8px・押し直し 0.3秒
   ※ この分布は仮定であり、初見プレイヤーの実測ではない。クリア率は「このモデルでの」値で、初見のクリア率とは別物。
"""
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import test_gameplay  # noqa: E402,F401
from test_gameplay import STAGE_1  # noqa: E402
import stage1_bot as bot  # noqa: E402

G1L = bot.gates(STAGE_1)["GATE1"][0]
G2L = bot.gates(STAGE_1)["GATE2"][0]
WS = (-600.0, -450.0)
AIM = dict(aim_sigma=8.0, retry_delay=0.3)
out, lines = {}, []


def log(s=""):
    print(s); lines.append(s)


def where(r):
    """死亡した区間。"""
    x = r.world.max_x + 24
    if x < G1L - 30:
        return "ゲート1より前"
    if "GATE2" not in r.arrive and r.world.player.rect.right <= G1L + 1:
        return "ゲート1"
    if r.world.player.rect.right <= G2L + 1 and "GATE2" in r.arrive:
        return "ゲート2"
    return "ゲート間"


# ---- B. 判断時間ごとの死亡率 -------------------------------------------------
delays = [round(i * 0.25, 2) for i in range(17)]
curve = {}
for ws in WS:
    rates = []
    for d in delays:
        n = dead = 0
        for dash in (True, False):
            for seed in range(10):
                r = bot.play(STAGE_1, policy="required", dash=dash, jitter=20, seed=seed, gate_delay=d,
                             gate2_delay=1.0, wall_start=ws, **AIM)
                n += 1; dead += r.state != "clear"
        rates.append(dead / n)
    curve[str(int(ws))] = rates
out["death_rate_by_gate1_think"] = dict(delays=delays, rates=curve)
log("## B. ゲート1で考える時間ごとの死亡率（ダッシュ有無×10通り、照準σ8px、ゲート2で1秒）")
log("考える秒数 : " + " ".join(f"{d:>5}" for d in delays))
for ws in WS:
    log(f"{int(ws):>10} : " + " ".join(f"{v:>5.0%}" for v in curve[str(int(ws))]))
for ws in WS:
    r = curve[str(int(ws))]
    first = next((d for d, v in zip(delays, r) if v > 0), None)
    half = next((d for d, v in zip(delays, r) if v >= 0.5), None)
    log(f"  {int(ws)}: 死亡が出始める {first}秒 / 半数が死ぬ {half}秒")

# ---- C. 仮のプレイヤーモデル -------------------------------------------------
N = 600
rng = random.Random(2026)
samples = [dict(dash=rng.random() < 0.5, seed=i, start_delay=rng.uniform(0, 1.0), gate_delay=rng.uniform(0, 4.0),
                gate2_delay=rng.uniform(0, 3.0), wrong=rng.random() < 0.15, air=rng.random() < 0.30)
           for i in range(N)]
model = {}
for ws in WS:
    res = []
    for s in samples:
        r = bot.play(STAGE_1, policy="required", dash=s["dash"], jitter=20, seed=s["seed"],
                     start_delay=s["start_delay"], gate_delay=s["gate_delay"], gate2_delay=s["gate2_delay"],
                     air_e02=s["air"], wrong_first={"GATE1": "E02"} if s["wrong"] else None,
                     wall_start=ws, max_time=40, **AIM)
        g1 = next((sw for sw in r.swaps if sw.target == "E03"), None)
        res.append(dict(clear=r.state == "clear", cause=r.world.death_cause,
                        where=None if r.state == "clear" else where(r),
                        t=r.world.elapsed, clicks=r.clicks, swaps=len(r.swaps), failed=dict(r.failed),
                        g1_wait=(g1.t - r.arrive["GATE1"][0]) if g1 and "GATE1" in r.arrive else None,
                        min_gap=r.min_gap))
    model[str(int(ws))] = res

out["model_samples"] = samples
summary = {}
log()
log(f"## C. 仮のプレイヤーモデル N={N}（-600 と -450 で同じ乱数）※初見のクリア率ではない")
for ws in WS:
    res = model[str(int(ws))]
    cl = [x for x in res if x["clear"]]
    deaths = {}
    for x in res:
        if not x["clear"]:
            k = f'{x["where"]}（{x["cause"]}）'
            deaths[k] = deaths.get(k, 0) + 1
    clicks = sum(x["clicks"] for x in res)
    swaps = sum(x["swaps"] for x in res)
    failed = {}
    for x in res:
        for k, v in x["failed"].items():
            failed[k] = failed.get(k, 0) + v
    ts = sorted(x["t"] for x in cl)
    waits = sorted(x["g1_wait"] for x in res if x["g1_wait"] is not None)
    s = dict(clear_rate=len(cl) / N, death_rate=1 - len(cl) / N, deaths=deaths,
             clear_time_median=statistics.median(ts), clear_time_p90=ts[int(len(ts) * 0.9)],
             teleport_success=swaps / clicks, clicks=clicks, swaps=swaps, failed=failed,
             g1_wait_median=statistics.median(waits) if waits else None,
             wrong_clear=sum(x["clear"] for x, sm in zip(res, samples) if sm["wrong"]) / max(1, sum(sm["wrong"] for sm in samples)))
    summary[str(int(ws))] = s
    log(f"### {int(ws)}")
    log(f"  クリア {len(cl)}/{N}（{s['clear_rate']:.1%}）、死亡率 {s['death_rate']:.1%}")
    log(f"  死亡の内訳: {deaths}")
    log(f"  クリア時間 中央値 {s['clear_time_median']:.2f}秒 / 90%点 {s['clear_time_p90']:.2f}秒")
    log(f"  テレポート成立率 {swaps}/{clicks} = {s['teleport_success']:.1%}（不成立の理由 {failed}）")
    log(f"  ゲート1到着から E03 交換までの実際の待ち（中央値）{s['g1_wait_median']:.2f}秒")
    log(f"  ゲート1で誤って E02 と交換した人のクリア率 {s['wrong_clear']:.1%}")
pair = [(a["clear"], b["clear"]) for a, b in zip(model["-600"], model["-450"])]
only600 = sum(a and not b for a, b in pair)
only450 = sum(b and not a for a, b in pair)
log(f"  対の比較: -600 だけクリア {only600} 件 / -450 だけクリア {only450} 件")
summary["paired"] = dict(only_600=only600, only_450=only450)
out["model_summary"] = summary
out["model_results"] = model

with open(os.path.join(HERE, "wall_compare_v2.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
with open(os.path.join(HERE, "wall_compare_v2_output.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
