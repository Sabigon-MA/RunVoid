"""ステージJSONの読み込みと検証。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pygame

import config

STAGE_DIR = Path(__file__).resolve().parent


class StageFormatError(ValueError):
    pass


@dataclass(frozen=True)
class RectDef:
    id: str
    x: float
    y: float
    w: float
    h: float

    def to_rect(self) -> pygame.FRect:
        return pygame.FRect(self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class EnemyDef:
    id: str
    type: str
    x: float
    foot_y: float


@dataclass(frozen=True)
class WallDef:
    start_x: float
    speed: float
    thickness: float


@dataclass(frozen=True)
class StageData:
    stage_id: int
    name: str
    resolution: tuple[int, int]
    tile_size: int
    theme: str
    spawn: tuple[float, float]
    wall: WallDef
    platforms: tuple[RectDef, ...]
    one_way_platforms: tuple[RectDef, ...]
    enemies: tuple[EnemyDef, ...]
    goal_x: float
    world_width: float
    kill_y: float


def _require(data: dict, key: str, where: str):
    if key not in data:
        raise StageFormatError(f"{where}: '{key}' がありません")
    return data[key]


def _rect_list(items, where: str) -> tuple[RectDef, ...]:
    out = []
    for i, item in enumerate(items):
        w = f"{where}[{i}]"
        r = RectDef(str(item.get("id", f"{where}{i}")),
                    float(_require(item, "x", w)), float(_require(item, "y", w)),
                    float(_require(item, "w", w)), float(_require(item, "h", w)))
        if r.w <= 0 or r.h <= 0:
            raise StageFormatError(f"{w}: 幅と高さは正の値にしてください")
        out.append(r)
    return tuple(out)


def parse_stage(data: dict) -> StageData:
    spawn = _require(data, "spawn", "stage")
    wall_raw = dict(config.WALL_DEFAULTS)
    wall_raw.update(data.get("wall", {}))
    platforms = _rect_list(_require(data, "platforms", "stage"), "platforms")
    one_ways = _rect_list(data.get("one_way_platforms", []), "one_way_platforms")
    enemies = tuple(
        EnemyDef(str(e.get("id", f"E{i}")), str(_require(e, "type", f"enemies[{i}]")),
                 float(_require(e, "x", f"enemies[{i}]")),
                 float(_require(e, "foot_y", f"enemies[{i}]")))
        for i, e in enumerate(data.get("enemies", []))
    )
    resolution = tuple(data.get("resolution", [config.SCREEN_WIDTH, config.SCREEN_HEIGHT]))
    goal_x = float(_require(data, "goal_x", "stage"))
    terrain_right = max((p.x + p.w for p in platforms), default=goal_x)
    world_width = float(data.get("world_width", max(goal_x, terrain_right)))
    kill_y = float(data.get("kill_y", resolution[1] + config.FALL_DEATH_MARGIN))
    return StageData(
        stage_id=int(data.get("stage_id", 0)),
        name=str(data.get("name", "")),
        resolution=(int(resolution[0]), int(resolution[1])),
        tile_size=int(data.get("tile_size", config.TILE_SIZE)),
        theme=str(data.get("theme", "twilight_ruins")),
        spawn=(float(_require(spawn, "x", "spawn")), float(_require(spawn, "y", "spawn"))),
        wall=WallDef(float(wall_raw["start_x"]), float(wall_raw["speed"]),
                     float(wall_raw["thickness"])),
        platforms=platforms,
        one_way_platforms=one_ways,
        enemies=enemies,
        goal_x=goal_x,
        world_width=world_width,
        kill_y=kill_y,
    )


def load_stage(name_or_path: str | Path = config.DEFAULT_STAGE) -> StageData:
    path = Path(name_or_path)
    if not path.is_absolute() and not path.exists():
        path = STAGE_DIR / path
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return parse_stage(data)
