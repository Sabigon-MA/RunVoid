"""初回の必須ゲート（ゲート1）で失敗したときの再挑戦時間: チェックポイントなし / ゲート手前チェックポイントあり（案）。

    cd game
    python stages/qa_stage1_v25/retry_compare.py   → retry_compare.txt / retry_compare.json

チェックポイントは実装しない。案の挙動は「出現位置と追跡壁の開始位置だけを変えたステージ」をメモリ上で作って模擬する
（敵・クールダウン・タイマーは最初から。ゲームのファイルは変更しない）。
時間の内訳:
    ゲート1で失敗するまで … 到着から壁に飲まれるまで（ゲート1で交換しなかった場合）
    死亡画面 … 0.6 秒は入力を受け付けない（ui/screens.py の delay）＋ リトライを押すまでの人の反応（仮定 0.5 秒、実測していない）
    作り直し … World(stage) の生成時間（実測、描画あり）
    ゲート1へ戻る … 出現からゲート1到着まで（ボット）
"""
import dataclasses
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import pygame  # noqa: E402
from test_gameplay import STAGE_1  # noqa: E402
import stage1_bot as bot  # noqa: E402
from stages.loader import WallDef  # noqa: E402
from systems.world import World  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
DEATH_LOCK, REACTION = 0.6, 0.5
SPEED = STAGE_1.wall.speed

World(STAGE_1)   # 背景のキャッシュを温める（2回目以降のリトライと同じ条件）
ts = []
for _ in range(10):
    t0 = time.perf_counter(); World(STAGE_1); ts.append(time.perf_counter() - t0)
REBUILD = statistics.median(ts)

lines, out = [], {}


def log(s=""):
    print(s); lines.append(s)


def stage_with(spawn_x, gap):
    return dataclasses.replace(STAGE_1, spawn=(float(spawn_x), 382.0),
                               wall=WallDef(float(spawn_x - gap), STAGE_1.wall.speed, STAGE_1.wall.thickness))


def measure(stage, dash):
    r = bot.play(stage, policy="none", dash=dash, max_time=40)
    arr_t, arr_gap = r.arrive["GATE1"]
    best = None
    d = 0.0
    while d <= 6:
        if bot.play(stage, policy="required", dash=dash, gate_delay=d, gate2_delay=0.0).state == "clear":
            best = d
        d = round(d + 0.05, 2)
    return arr_t, arr_gap, best


log(f"死亡画面の入力待ち {DEATH_LOCK}秒 + リトライを押す反応 {REACTION}秒（仮定）+ 作り直し {REBUILD * 1000:.0f}ms（実測の中央値）")
plans = [("なし（ステージの最初から）", None, None),
         ("案A: 区間3の穴を越えた所（x=1,560）、壁との距離 800px", 1560, 800),
         ("案B: 台座の先（x=2,100、ゲート1の 220px 手前）、壁との距離 800px", 2100, 800),
         ("案C: 台座の先（x=2,100）、壁との距離 650px", 2100, 650)]
for ws in (-600.0, -450.0):
    log(f"\n## 追跡壁の開始 {int(ws)}")
    for name, sx, gap in plans:
        st = dataclasses.replace(STAGE_1, wall=WallDef(ws, SPEED, STAGE_1.wall.thickness)) if sx is None else stage_with(sx, gap)
        if sx is not None and ws != -600.0:
            continue        # チェックポイント案は壁の開始位置に依存しない（出現時の距離で決まる）
        for dash in (False, True):
            arr_t, arr_gap, think = measure(st, dash)
            fail_at_gate = arr_gap / SPEED
            cycle = arr_t + fail_at_gate + DEATH_LOCK + REACTION + REBUILD
            back = DEATH_LOCK + REACTION + REBUILD + arr_t
            key = f"{int(ws)}|{name}|{'dash' if dash else 'nodash'}"
            out[key] = dict(arrive=arr_t, gap=arr_gap, think_max=think, death_to_gate=back, cycle=cycle,
                            attempts_per_min=60 / cycle)
            log(f"{name} / {'ダッシュあり' if dash else 'ダッシュなし'}: ゲート1まで {arr_t:.2f}秒、到着時の壁との距離 {arr_gap:.0f}px、"
                f"ゲート1で考えられる最長 {think}秒 → 死亡からゲート1に戻るまで {back:.2f}秒、"
                f"ゲート1で考えきって失敗する1周 {cycle:.2f}秒（1分に {60 / cycle:.1f} 回）")
with open(os.path.join(HERE, "retry_compare.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
with open(os.path.join(HERE, "retry_compare.json"), "w", encoding="utf-8") as f:
    json.dump(dict(rebuild=REBUILD, death_lock=DEATH_LOCK, reaction_assumed=REACTION, plans=out), f, ensure_ascii=False, indent=1)
