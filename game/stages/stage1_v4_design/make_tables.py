"""v4data.py から座標付きの地形配置表・敵配置表・チェックポイント表（TABLES_v4.md）を書き出す。
game フォルダから実行する: python stages/stage1_v4_design/make_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v4data as D  # noqa: E402

KIND = {"solid": "固体", "oneway": "すり抜け"}
LAYER = {"upper": "上層", "mid": "中層", "lower": "下層", "deep": "地下", "gate": "城門"}


def area_of(x):
    for a, x0, x1, *_ in D.AREAS:
        if x0 <= x < x1:
            return a
    return D.AREAS[-1][0]


def main():
    out = ["# ステージ1 v4.0 設計案: 座標表", "",
           "`v4data.py` から `make_tables.py` で生成（手で編集しない）。座標はワールド座標（px）。y は下向きが正。",
           f"幅 {D.WORLD_W}、縦の範囲 {D.WORLD_TOP}〜{D.WORLD_BOTTOM}、落下死ライン {D.KILL_Y}、"
           f"出現位置（足元）{D.SPAWN}、ゴール x={D.GOAL_X}。", ""]
    out += ["## 1. 地形", ""]
    for a, x0, x1, name, theme in D.AREAS:
        out += [f"### {a} {name}（x={x0}〜{x1}）", "", theme, "",
                "| ID | 種類 | 層 | x | 上面 y | 幅 | 下端 y | 備考 |", "|---|---|---|---|---|---|---|---|"]
        for t in D.TERRAIN:
            if area_of(t["x0"]) == a:
                out.append(f"| {t['id']} | {KIND[t['kind']]}{'（城門）' if t['style'] == 'sealed_gate' else ''} | "
                           f"{LAYER[t['layer']]} | {t['x0']} | {t['top']} | {t['x1'] - t['x0']} | {t['bottom']} | {t['note']} |")
        out.append("")
    out += ["## 2. 敵（25体）", "", "| ID | 種類 | エリア | x | 足元 y | 役割 |", "|---|---|---|---|---|---|"]
    for eid, ty, x, fy, a, role in D.ENEMIES:
        out.append(f"| {eid} | {'影翔け' if ty == 'shadow_flier' else '影這い'} | {a} | {x} | {fy} | {role} |")
    n_c = sum(e[1] == "shadow_crawler" for e in D.ENEMIES)
    out += ["", f"影這い {n_c} 体、影翔け {len(D.ENEMIES) - n_c} 体。", ""]
    out += ["## 3. チェックポイント", "", "| ID | 有効になる x | 再開位置（足元） | 説明 |", "|---|---|---|---|"]
    for cid, x, sp, note in D.CHECKPOINTS:
        out.append(f"| {cid} | {x} | {sp} | {note} |")
    (HERE / "TABLES_v4.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("saved TABLES_v4.md")


if __name__ == "__main__":
    main()
