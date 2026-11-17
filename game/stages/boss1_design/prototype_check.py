"""ステージ1ボス戦の設計検証（実装前）。ゲームのコード・ステージファイルは変更しない。

    cd game
    python stages/boss1_design/prototype_check.py   → prototype_check.txt / arena_layout.png

stage_1.json に設計案の闘技場・脱出区間をメモリ上で足し、既存の Boss 基底クラスを継承した試作ボス
（単発の直線弾だけを撃つ）で、既存のテレポート・飛び道具・追跡壁・クリア条件の挙動を測る。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import pygame  # noqa: E402
import config  # noqa: E402
from bosses.base import Boss  # noqa: E402
from stages.loader import STAGE_DIR, parse_stage  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.targeting import is_targetable  # noqa: E402
from systems.world import World  # noqa: E402
import stage1_bot as bot  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
DT = config.FIXED_DT
FLOOR = 422.0

# ---------------------------------------------------------------------------
# 設計案の座標（ARENA_SPEC.md の A 章と同じ値）
ARENA_L, ARENA_R = 3480, 4440
LEDGES = [(3640, 330, 160, 16), (4080, 330, 160, 16)]
BOSS_X = 4360
ADD_PLATFORMS = [
    ("A0", 3360, 120),          # 闘技場への通路
    ("ARENA", ARENA_L, ARENA_R - ARENA_L),
    ("X1", 4440, 360),          # 脱出区間
    ("X2", 4880, 440),
    ("X3", 5400, 440),
]
GOAL_X, WORLD_W = 5760, 5840


def arena_raw():
    raw = json.load(open(STAGE_DIR / "stage_1.json", encoding="utf-8"))
    for pid, x, w in ADD_PLATFORMS:
        raw["platforms"].append({"id": pid, "x": x, "y": 422, "w": w, "h": 118})
    raw.setdefault("one_way_platforms", [])
    for i, (x, y, w, h) in enumerate(LEDGES):
        raw["one_way_platforms"].append({"id": f"L{i + 1}", "x": x, "y": y, "w": w, "h": h})
    raw["goal_x"], raw["world_width"] = GOAL_X, WORLD_W
    return raw


STAGE = parse_stage(arena_raw())


class ProtoBoss(Boss):
    """試作: HP 3、自傷 1。予告 0.9 秒の後に主人公へ直線弾を1発。間隔 3.0 秒。"""
    display_name = "試作ボス"

    def __init__(self, speed=180.0, auto=True):
        super().__init__(BOSS_X, FLOOR, "BOSS", dict(hp=3, projectile_self_damage=1, projectile_speed=speed))
        self.contact_damage = 0
        self.t = 0.0
        self.auto = auto
        self.facing = -1

    def should_engage(self, world):
        return world.player.rect.left >= ARENA_L + 20

    def update_ai(self, dt, world):
        if not self.auto:
            return
        self.t += dt
        if self.t >= 3.9:
            self.t = 0.0
            self.fire_at_player(world)


lines = []


def log(s=""):
    print(s); lines.append(str(s))


def arena_world(px, boss=None, lock=True):
    w = World(STAGE, with_graphics=False)
    w.enemies = [e for e in w.enemies]          # 通常区間の敵はそのまま
    boss = boss or ProtoBoss(auto=False)
    w.enemies.append(boss)
    w.required_bosses = {boss}
    w.player.rect.topleft = (px, 382)
    w.camera.snap_to(w.player.rect)
    if lock:
        w.camera.x = ARENA_L
    w.wall.segments[0].front_x = 2600.0
    return w, boss


def step(w, inp, n=1, lock=True):
    for _ in range(n):
        if w.update(DT, inp):
            inp.clear_edges()
        if lock and w.active_boss is not None:
            w.camera.x = ARENA_L                    # 設計案のカメラ固定を模擬
        if w.state != "playing":
            break


# ---------------------------------------------------------------------------
log("# ステージ1ボス戦 設計検証（試作ボス、既存コード）")
log(f"闘技場 x={ARENA_L}〜{ARENA_R}（幅 {ARENA_R - ARENA_L}）、床 y={FLOOR:.0f}、一方通行の足場 {LEDGES}、ボス足元 ({BOSS_X},{FLOOR:.0f})")

# 1. 画面内での交換（カメラ固定あり／なし）
log("\n## 1. 画面内で交換できるか")
for lock in (False, True):
    ok = tot = 0
    for px in range(ARENA_L + 20, BOSS_X - 120, 40):
        w, boss = arena_world(px, lock=lock)
        inp = InputState(); step(w, inp, 5, lock=lock)
        tot += 1
        ok += is_targetable(boss, w.camera)
    log(f"カメラ固定{'あり' if lock else 'なし（通常の追従）'}: 主人公の位置 {tot} 通りのうち、ボスが画面内で交換対象になる {ok} 通り")
w, boss = arena_world(3600)
inp = InputState(); step(w, inp, 5)
pf, bf = w.player.foot_center, boss.foot_center
bot.click(w, inp, boss); step(w, inp)
log(f"地上で交換: {w.teleport.last_result.reason}、主人公 {pf[0]:.0f}→{w.player.foot_center[0]:.0f}、ボス {bf[0]:.0f}→{boss.foot_center[0]:.0f}")

# 空中・足場の上での交換
for h in (0, 24, 48, 60, 90, 140):
    w, boss = arena_world(3600)
    inp = InputState(); step(w, inp, 5)
    w.player.rect.bottom = FLOOR - h
    w.player.on_ground = False; w.player.vy = 0.0
    r = w.teleport.try_teleport(w, boss)
    log(f"主人公が床から {h:3d}px 上（空中）で交換: {r.reason}")
w, boss = arena_world(3700)
inp = InputState(); step(w, inp, 3)
w.player.rect.bottom = 330; w.player.vy = 0; step(w, inp, 3)
r = w.teleport.try_teleport(w, boss)
log(f"主人公が一方通行の足場（y=330）の上で交換: {r.reason}、ボスの足元 y={boss.foot_y:.0f}")

# 2. 弾の自傷: 交換の遅れごとの結果
log("\n## 2. 単発の直線弾: 発射から交換までの時間ごとの結果（ボスに命中 / 主人公に命中 / どちらにも当たらない）")
windows = {}
for speed in (180.0, 240.0, 288.0):
    for px in (3640, 3840, 4040):
        res = []
        d = 0
        while True:
            w, boss = arena_world(px, ProtoBoss(speed=speed, auto=False))
            inp = InputState(); step(w, inp, 5)
            proj = boss.fire_at_player(w)
            step(w, inp, d)
            if proj.done:
                break
            hb, hp = boss.hp, w.player.hp
            bot.click(w, inp, boss); step(w, inp)
            if not w.teleport.last_result.ok:
                res.append("B"); d += 1; continue
            for _ in range(600):
                step(w, inp)
                if proj.done:
                    break
            res.append("H" if boss.hp < hb else ("P" if w.player.hp < hp else "-"))
            d += 1
        dist = BOSS_X - (px + 12)
        hit = [i for i, c in enumerate(res) if c == "H"]
        windows[(speed, px)] = res
        span = f"{hit[0] * DT:.2f}〜{hit[-1] * DT:.2f}秒" if hit else "なし"
        seq = "".join(res)
        log(f"弾速 {speed:.0f}、距離 {dist:.0f}px: 命中する交換時刻 {span}（全 {len(res)} フレーム中 {len(hit)}） "
            f"先頭 {seq[:12]} … 末尾 {seq[-14:]}")
log("記号: H=ボスに命中 P=主人公に命中 -=どちらにも当たらない B=交換不成立。1文字=1フレーム（1/60秒）")

# 3. 飛行中の弾が複数あるときの交換
log("\n## 3. 弾が3発飛んでいる間に1回交換した場合")
w, boss = arena_world(3640, ProtoBoss(speed=180, auto=False))
inp = InputState(); step(w, inp, 5)
ps = []
for i in range(3):
    ps.append(boss.fire_at_player(w)); step(w, inp, 15)
bot.click(w, inp, boss); step(w, inp)
for _ in range(400):
    step(w, inp)
log(f"ボスの HP 3 → {boss.hp}（生存 {boss.alive}）: 1回の交換で飛行中の弾すべてが自傷になる")

# 4. 直接攻撃なしで撃破 → 壁・クリア条件
log("\n## 4. 撃破までの流れ（既存コードのまま）")
w, boss = arena_world(3560, ProtoBoss(speed=180, auto=True))
w.wall.segments[0].front_x = 3000.0
inp = InputState()
step(w, inp, 2)
log(f"戦闘開始: engaged={boss.engaged} 壁停止={w.wall.paused} 壁の前面 x={w.wall.front_x:.0f}")
wall_before = w.wall.front_x
swaps = 0
t = 0
while boss.alive and w.state == "playing" and t < 60 * 40:
    bot.release_click(inp)
    flying = [a for a in w.combat.attacks if a.owner is boss and not getattr(a, "self_harm_armed", False)]
    if flying and w.teleport.ready:
        a = flying[0]
        # 発射から 0.3 秒以上たち、主人公まで 120px 以上ある間に交換する
        if a.timer >= 0.3 and abs(a.x - w.player.rect.centerx) > 120:
            bot.click(w, inp, boss); swaps += 1
    step(w, inp); t += 1
log(f"撃破: alive={boss.alive} 死因={boss.death_cause} 交換 {swaps} 回 経過 {w.elapsed:.1f}秒 主人公HP {w.player.hp}")
log(f"戦闘中の壁の移動量: {w.wall.front_x - wall_before:.0f}px（停止していた）")
log(f"撃破直後: 壁停止={w.wall.paused} active_boss={w.active_boss} ステージの状態={w.state}")
log(f"→ 現在のコードでは撃破した瞬間にクリア（{w.state}）。脱出区間を走らせるにはクリア条件の変更が必要")
gap = w.player.rect.left - w.wall.front_x
log(f"撃破時の主人公と壁の距離 {gap:.0f}px（壁は戦闘開始時の位置から再開する）")

# 5. ボスを倒さずにゴールへ
log("\n## 5. ボスが生きている間にゴールへ着いた場合")
w, boss = arena_world(3560, ProtoBoss(auto=False))
inp = InputState(); step(w, inp, 2)
w.player.rect.right = GOAL_X + 1
step(w, inp, 3, lock=False)
log(f"状態={w.state}（クリアしない）。ただし闘技場の右側に障害物がないため、主人公はボスを無視して脱出区間へ走れる（二段ジャンプでボスの上を越えられる）")

# 6. 近景装飾の繰り返し
log("\n## 6. 近景装飾（周期 3,360px）が闘技場・脱出区間に出る位置")
deco = json.load(open(STAGE_DIR / "stage_1.json", encoding="utf-8"))["background"]["decorations"]["placements"]
for p in deco:
    x2 = p["x"] + 3360
    tag = "闘技場" if ARENA_L <= x2 < ARENA_R else ("脱出区間" if x2 >= ARENA_R else "通路")
    log(f"{p['sprite']}@{p['x']} → 2周目 x={x2}（{tag}。パララックス 0.75 のため画面上の位置はカメラにより変わる）")

with open(os.path.join(HERE, "prototype_check.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

# ---------------------------------------------------------------------------
# 闘技場の配置図（実際の描画＋注記）と、通常区間の終わりからゴールまでの全体図
from ui import fonts  # noqa: E402


def text(s, msg, pos, col=(255, 255, 255), size=14, bg=True):
    img = fonts.get_font(size, True).render(msg, True, col)
    if bg:
        b = pygame.Surface((img.get_width() + 8, img.get_height() + 4), pygame.SRCALPHA); b.fill((0, 0, 0, 170))
        s.blit(b, (pos[0] - 4, pos[1] - 2))
    s.blit(img, pos)


w, boss = arena_world(3560, ProtoBoss(auto=False))
w.with_graphics = True
from stages.renderer import TerrainRenderer, make_background  # noqa: E402
w.background = make_background(STAGE.theme, 960, 540, STAGE.background)
w.terrain_renderer = TerrainRenderer(STAGE)
inp = InputState(); step(w, inp, 3)
boss.fire_at_player(w); step(w, inp, 50)
shot = pygame.Surface((960, 540)); w.draw(shot)
ov = pygame.Surface((960, 540), pygame.SRCALPHA)
cx = ARENA_L
for bx in (ARENA_L - 24, ARENA_R):                               # 出入口の障壁（設計案）
    ov.fill((120, 236, 222, 70), (bx - cx, 0, 24, 422))
pygame.draw.rect(ov, (255, 255, 255, 200), (0, 0, 960, 540), 2)
for (x, y, ww, hh) in LEDGES:
    pygame.draw.rect(ov, (255, 230, 120, 220), (x - cx, y, ww, hh), 2)
pygame.draw.rect(ov, (255, 120, 120, 230), boss.body_rect.move(-cx, 0), 2)
pygame.draw.rect(ov, (120, 200, 255, 230), w.player.rect.move(-cx, 0), 2)
shot.blit(ov, (0, 0))
text(shot, f"カメラ固定 x={ARENA_L}（闘技場 {ARENA_L}〜{ARENA_R}、幅960 = 1画面）", (12, 12))
text(shot, "入口の障壁 x=3456〜3480（戦闘開始で閉じる）", (12, 40), (150, 255, 240))
text(shot, "出口の障壁 x=4440〜4464（撃破後に崩れる）", (600, 40), (150, 255, 240))
for i, (x, y, ww, hh) in enumerate(LEDGES):
    text(shot, f"足場L{i + 1} x={x}〜{x + ww} y={y}（一方通行）", (x - cx - 10, y - 30), (255, 230, 120), 13)
text(shot, f"ボス 64×96 足元 ({BOSS_X},422)", (boss.body_rect.left - cx - 130, 440), (255, 150, 150), 13)
text(shot, "主人公の戦闘開始位置 x≈3500〜3560", (40, 440), (150, 210, 255), 13)
text(shot, "床 y=422（穴なし）", (420, 470), (230, 230, 230), 13)
text(shot, "単発弾（弾速180）が飛行中 → 今交換するとボスに命中", (330, 360), (255, 160, 230), 13)

# 全体図（x 3000〜5840 を 0.4 倍）
S = 0.4
over = pygame.Surface((int((WORLD_W - 3000) * S) + 20, 230)); over.fill((24, 18, 22))
def X(x): return int((x - 3000) * S) + 10  # noqa: E704
for p in STAGE.platforms:
    if p.x + p.w < 3000:
        continue
    col = (90, 220, 210) if p.style == "sealed_gate" else (70, 60, 64)
    top = max(p.y, 40)
    pygame.draw.rect(over, col, (X(max(p.x, 3000)), int(top * S) + 20, int((p.x + p.w - max(p.x, 3000)) * S), int((540 - top) * S)))
for (x, y, ww, hh) in LEDGES:
    pygame.draw.rect(over, (255, 230, 120), (X(x), int(y * S) + 20, int(ww * S), 3))
pygame.draw.rect(over, (255, 255, 255), (X(ARENA_L), 20, int(960 * S), int(540 * S)), 1)
marks = [(3200, "旧ゴール"), (3420, "CP2"), (ARENA_L, "闘技場"), (BOSS_X, "ボス"), (ARENA_R, "出口"), (4800, "穴"),
         (5320, "穴"), (GOAL_X, "ゴール")]
for i, (x, name) in enumerate(marks):
    pygame.draw.line(over, (255, 200, 120), (X(x), 16), (X(x), 210), 1)
    text(over, f"{name} {x}", (X(x) + 2, 2 + (i % 2) * 196), (255, 220, 150), 11, bg=False)
pygame.draw.rect(over, (255, 120, 120), (X(BOSS_X - 32), int(326 * S) + 20, int(64 * S), int(96 * S)))
out = pygame.Surface((max(960, over.get_width()), 540 + 8 + over.get_height())); out.fill((255, 255, 255))
out.blit(shot, (0, 0)); out.blit(over, (0, 548))
pygame.image.save(out, os.path.join(HERE, "arena_layout.png"))
print("saved arena_layout.png")
