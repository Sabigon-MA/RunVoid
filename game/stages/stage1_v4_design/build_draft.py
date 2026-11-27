"""v4data.py から設計検証用のステージ JSON（stage_1_v4_draft.json）を書き出す。

- 現行のローダー（stages/loader.py）でそのまま読める形にする（検証で実際の物理を使うため）。
- 現行の形式にない項目（複数チェックポイント・追跡壁の区間・カメラの区間・エリア）は
  "v4_proposal" の下に置く。現行のローダーは知らない項目を無視する。
- 正式なステージデータではない（stages/ 直下には置かない）。
game フォルダから実行する: python stages/stage1_v4_design/build_draft.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v4data as D  # noqa: E402

OUT = HERE / "stage_1_v4_draft.json"


def rect_json(t):
    style = t["style"]
    if style == "ground" and t["layer"] in (D.DEEP,) and t["kind"] == "solid":
        style = "underground"
    d = {"id": t["id"], "x": t["x0"], "y": t["top"], "w": t["x1"] - t["x0"], "h": t["bottom"] - t["top"]}
    if style != "ground":
        d["style"] = style
    return d


def draft_dict(enemy_ids=None, wall=None):
    """enemy_ids: 含める敵の ID（None なら全員）。wall: {"start_x", "speed"} の上書き。"""
    solids = [rect_json(t) for t in D.TERRAIN if t["kind"] == "solid"]
    ones = [rect_json(t) for t in D.TERRAIN if t["kind"] == "oneway"]
    enemies = [{"id": i, "type": ty, "x": x, "foot_y": fy} for i, ty, x, fy, *_ in D.ENEMIES
               if enemy_ids is None or i in enemy_ids]
    cp = D.CHECKPOINTS[0]
    return {
        "stage_id": 1, "name": "黄昏の廃王国", "version": "4.0-draft",
        "resolution": [960, 540], "tile_size": 32, "theme": "twilight_ruins",
        "camera_bounds": {"top": D.WORLD_TOP, "bottom": D.WORLD_BOTTOM},
        "kill_y": D.KILL_Y,
        "spawn": {"x": D.SPAWN[0], "y": D.SPAWN[1] - 40},
        "wall": wall or {"start_x": -600, "speed": 300, "thickness": 32},
        # 現行のローダーが読めるのは1か所だけなので、先頭の CP1 を入れておく
        "checkpoint": {"id": cp[0], "x": cp[1], "y": cp[2][1] - 40, "wall_gap": 800},
        "platforms": solids,
        "one_way_platforms": ones,
        "enemies": enemies,
        "goal_x": D.GOAL_X,
        "world_width": D.WORLD_W,
        "v4_proposal": {
            "areas": [{"id": a, "x0": x0, "x1": x1, "name": n} for a, x0, x1, n, _ in D.AREAS],
            "checkpoints": [{"id": i, "x": x, "spawn_foot": list(sp)} for i, x, sp, _ in D.CHECKPOINTS],
        },
    }


def main():
    OUT.write_text(json.dumps(draft_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT.name, f"solids={sum(t['kind'] == 'solid' for t in D.TERRAIN)}",
          f"oneway={sum(t['kind'] == 'oneway' for t in D.TERRAIN)}", f"enemies={len(D.ENEMIES)}")


if __name__ == "__main__":
    main()
