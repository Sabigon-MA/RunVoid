"""(a) 変異試験: 城門に抜け道を作ったステージで、テストのランダム入力が抜け道を見つけられるか
(b) 本番ステージで大規模ランダム入力（1500回×8秒×2門）"""
import os, sys, dataclasses, unittest
GAME = sys.argv[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import test_gameplay  # noqa
import test_stage1_layout as T


def with_gate(**chg):
    st = T.STAGE_1
    plats = tuple(dataclasses.replace(p, **chg) if p.id == "GATE1" else p for p in st.platforms)
    return dataclasses.replace(st, platforms=plats)


case = T.GateIsImpassableTests("test_random_input_never_passes_gate1")
orig = T.STAGE_1
for name, chg in (("上が低い城門 y=250", dict(y=250, h=450)), ("下が短い城門 h=540", dict(h=540)),
                  ("上が低い城門 y=180", dict(y=180, h=520))):
    T.STAGE_1 = with_gate(**chg)
    try:
        case._fuzz(1700, "GATE1", runs=120, frames=480, seed=11)
        print(f"(a) {name}: 抜け道を検出できず")
    except AssertionError as e:
        print(f"(a) {name}: 検出 → {str(e)[:60]}")
T.STAGE_1 = orig

for gid, sx, seed in (("GATE1", 1700, 101), ("GATE2", 2450, 202)):
    worst = case._fuzz(sx, gid, runs=1500, frames=480, seed=seed)
    print(f"(b) {gid}: 1500回×8秒 越えなし。到達した最大 rect.right={worst:.1f}（城門左端 {T.GATES[gid][0]}）")
