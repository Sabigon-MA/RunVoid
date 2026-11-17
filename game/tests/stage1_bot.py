"""ステージ1（v2.5 C案）の自動操作ボット。テスト用の共通部品（unittest の探索対象ではない）。

人間の操作に近い単純な方針で 1 プレイする:
    - 右を押し続け、決めた位置で踏み切る（必要なら頂点で二段ジャンプ）
    - B01 を越えた後の下降中は右を離して G02 に降りる（越えすぎて穴に落ちないため）
    - 壁に阻まれて止まったら跳び直す（城門の前では跳ばない）
    - ダッシュで段の縁から飛び出して着地しないまま穴の上に出たら、空中で跳ぶ（ジャンプが残っていれば）
    - 地上ではダッシュを使う（dash=False で使わない）
    - テレポートは実際の入力と同じ経路（MOUSEBUTTONDOWN イベント → InputState → find_target）で行う

テレポートの方針 policy:
    "none"     使わない
    "required" 城門の前に着いてから gate_delay 秒後（ゲート2は gate2_delay 秒後）に、門の向こうの敵と交換する
    "expert"   画面内で 250px 以上前にいる最も遠い敵と、使えるようになり次第交換する（城門の前では required と同じ）
air_e02=True なら、区間3の穴の上空で E02 が見えたら空中で交換する。
wrong_first={"GATE1": "E02"} なら、その城門で正しい相手より先に誤って指定の敵と交換する（誤クリックの回復性の検証用）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import pygame

import config
from systems.targeting import is_targetable
from systems.world import PLAYING, World

DT = config.FIXED_DT

# (踏み切る rect.right の下限, 足場の上面, 二段ジャンプするか)。上限は +80px
ROUTE = [(362, 422, False),    # S01（高さ32）
         (745, 422, False),    # 穴 760-870
         (930, 422, False),    # B01（高さ120）
         (1288, 438, True),    # 降り段 G02s から穴 1300-1520
         (1915, 422, False),   # 台座 PED（高さ32）
         (2888, 438, False)]   # 降り段 G04s から穴 2900-2980
BRAKES = [(1075, 1200)]        # B01 を越えた後の下降中は右を離す
GATE_TARGETS = {"GATE1": "E03", "GATE2": "E04"}


def gates(stage) -> dict[str, tuple[float, float, str]]:
    """{門のID: (左端x, 右端x, 向こう側の交換相手)}"""
    return {p.id: (p.x, p.x + p.w, GATE_TARGETS[p.id]) for p in stage.platforms if p.style == "sealed_gate"}


def click(w: World, inp, enemy) -> None:
    """敵の当たり判定の中心を、実際のマウス入力と同じイベント経路でクリックする。"""
    pos = w.camera.to_screen(*enemy.hurtbox.center)
    inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def release_click(inp) -> None:
    inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=inp.mouse_pos))


@dataclass
class Swap:
    t: float
    target: str
    airborne: bool
    before: pygame.FRect
    after: pygame.FRect
    wall_gap: float
    jumps_used_after: int


@dataclass
class Result:
    world: World
    swaps: list[Swap] = field(default_factory=list)
    arrive: dict = field(default_factory=dict)       # {門のID: (到着時刻, 壁との差)}
    min_gap: float = 1e9
    rows: list = field(default_factory=list)          # record=True のときの毎ステップの状態
    clicks: int = 0                                   # 交換を狙ったクリックの回数
    failed: dict = field(default_factory=dict)        # 不成立の理由ごとの回数（"miss": カーソル下に敵がいない）

    @property
    def state(self):
        return self.world.state


def play(stage, *, policy="none", dash=True, gate_delay=0.0, gate2_delay=None, air_e02=False,
         jitter=0, seed=0, max_time=25.0, with_graphics=False, record=False, wall_start=None,
         wrong_first=None, start_delay=0.0, aim_sigma=0.0, retry_delay=0.0,
         from_checkpoint=False) -> Result:
    """start_delay: 開始直後に何もしない秒数 / aim_sigma: クリック位置のずれ（正規分布の標準偏差 px、
    0 なら当たり判定の中心ちょうど）/ retry_delay: 交換が成立しなかったクリックの後、次に押すまでの秒数。
    3つとも既定値では従来どおり（物理トレースはこの既定値で記録）。
    from_checkpoint: ステージのチェックポイントから始める（v2.5）。"""
    from systems.input import InputState
    from systems.targeting import find_target
    rng = random.Random(seed)
    arng = random.Random(seed * 7919 + 1)     # 照準のずれ用（踏み切り位置の乱数列は変えない）
    next_click = 0.0
    w = World(stage, with_graphics=with_graphics, from_checkpoint=from_checkpoint)
    if wall_start is not None:
        w.wall.segments[0].front_x = wall_start
    g = gates(stage)
    res = Result(w)
    inp = InputState()
    inp.simulate_press("right")
    p = w.player
    route = [(x + rng.randint(-jitter, jitter), s, d) for x, s, d in ROUTE]
    from stages.renderer import find_pits
    pits = [(x0, x1) for x0, x1, _ in find_pits([r.to_rect() for r in stage.platforms], stage.world_width,
                                                stage.resolution[1])]
    used, double, hold = set(), False, 0
    for _ in range(int(max_time / DT)):
        if w.elapsed < start_delay - 1e-9:          # 開始直後のためらい（入力なし）
            for a in ("right", "jump", "dash"):
                inp.simulate_release(a)
            if w.update(DT, inp):
                inp.clear_edges()
            res.min_gap = min(res.min_gap, p.rect.left - w.wall.front_x)
            if w.state != PLAYING:
                break
            continue
        if not p.on_ground and p.vy > 0 and any(a <= p.rect.right <= b for a, b in BRAKES):
            inp.simulate_release("right")
        elif not inp.held("right"):
            inp.simulate_press("right")
        if hold > 0:
            hold -= 1
            if hold == 0:
                inp.simulate_release("jump")
        if double and p.vy >= -30 and not p.on_ground:
            inp.simulate_release("jump"); inp.simulate_press("jump")
            hold, double = 40, False
        jumped = False
        # 地上ダッシュのまま段の縁から飛び出し、降り段に着地しないまま穴の上に出たら空中で跳ぶ（人間なら当然やる）。
        # 通常の踏み切り（上昇中に穴へ出る）では発動しない
        if (not p.on_ground and hold == 0 and p.vy >= 0 and p.jumps_used < p.max_jumps
                and any(x0 - 4 <= p.rect.right <= x0 + 24 for x0, _ in pits)):
            inp.simulate_release("jump"); inp.simulate_press("jump")
            hold, jumped = 40, True
        if p.on_ground:
            for i, (x, surf, dbl) in enumerate(route):
                if i not in used and abs(p.rect.bottom - surf) < 1 and x <= p.rect.right <= x + 80:
                    used.add(i); inp.simulate_release("jump"); inp.simulate_press("jump")
                    hold, double, jumped = 40, dbl, True
                    break
        if (not jumped and p.on_ground and hold == 0 and inp.held("right")
                and w.terrain.overlaps_solid(p.rect.move(2, 0))
                and not any(gl - 30 <= p.rect.right <= gl + 1 for gl, _, _ in g.values())):
            inp.simulate_release("jump"); inp.simulate_press("jump")
            hold, jumped = 40, True
        near = any(i not in used and abs(p.rect.bottom - s) < 1 and x - 140 <= p.rect.right < x
                   for i, (x, s, _) in enumerate(route))
        if dash and p.on_ground and p.dash_cooldown <= 0 and not jumped and not near:
            inp.simulate_press("dash")
        else:
            inp.simulate_release("dash")
        for gid, (gl, _, _) in g.items():
            if gid not in res.arrive and p.on_ground and p.rect.right >= gl - 2 and p.rect.left < gl:
                res.arrive[gid] = (w.elapsed, p.rect.left - w.wall.front_x)
        target = None
        if policy != "none" and w.teleport.ready:
            vis = [e for e in w.enemies if is_targetable(e, w.camera)]
            if policy == "expert":
                ahead = [e for e in vis if e.x - p.rect.centerx > 250]
                if ahead:
                    target = max(ahead, key=lambda e: e.x)
            if target is None and air_e02 and not p.on_ground and 1300 < p.rect.centerx < 1520:
                target = next((e for e in vis if e.enemy_id == "E02"), None)
            if target is None:
                for gid, (gl, _, tid) in g.items():
                    delay = gate2_delay if gid == "GATE2" and gate2_delay is not None else gate_delay
                    if gid in res.arrive and p.rect.right <= gl + 1 and w.elapsed - res.arrive[gid][0] >= delay:
                        wrong = (wrong_first or {}).get(gid)
                        if wrong and wrong not in {s.target for s in res.swaps}:
                            # 誤った相手が画面にいなければ（壁に飲まれた等）正しい相手を押す
                            target = next((e for e in vis if e.enemy_id == wrong), None)
                        if target is None:
                            target = next((e for e in vis if e.enemy_id == tid), None)
        if target is not None and w.elapsed < next_click - 1e-9:
            target = None
        # 体の中心が画面に入るまでは押さない（画面外の点はクリックできない。外れても物理は変わらない）
        if target is not None and not w.camera.view_rect.collidepoint(target.hurtbox.center):
            target = None
        selected = None
        if target is not None:
            cx, cy = target.hurtbox.center
            if aim_sigma > 0:
                cx, cy = cx + arng.gauss(0, aim_sigma), cy + arng.gauss(0, aim_sigma)
            pos = w.camera.to_screen(cx, cy)
            selected = find_target(w.enemies, w.camera, w.camera.to_world(*pos))
            inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
            res.clicks += 1
        before, count, grounded = p.rect.copy(), w.teleport.count, p.on_ground
        if w.update(DT, inp):
            inp.clear_edges()
        if target is not None:
            release_click(inp)
        gap = p.rect.left - w.wall.front_x
        res.min_gap = min(res.min_gap, gap)
        if w.teleport.count > count:
            res.swaps.append(Swap(w.elapsed, selected.enemy_id, not grounded, before, p.rect.copy(), gap, p.jumps_used))
        elif target is not None:
            reason = "miss" if selected is None else w.teleport.last_result.reason
            res.failed[reason] = res.failed.get(reason, 0) + 1
            next_click = w.elapsed + retry_delay
        if record:
            res.rows.append([round(v, 4) for v in (p.rect.x, p.rect.y, p.vx, p.vy, w.wall.front_x, w.camera.x)]
                            + [int(p.on_ground), p.hp, w.teleport.count]
                            + [[e.enemy_id, round(e.x, 4), round(e.foot_y, 4)] for e in w.enemies])
        if w.state != PLAYING:
            break
    return res
