"""gate1_targets.png と実際のテレポート判定の照合。

    cd game
    python stages/qa_stage1_v25/verify_gate1_targets.py   → verify_gate1_targets.txt / gate1_pick_overlay.png / gate1_e02_window.png

1. 画像と同じ状態（shots.py と同じ手順: 壁なし、主人公をゲート1の左に置き 2.0 秒、カーソルは E03）を作り直し、
   注記なしの描画が画像の注記以外の画素と一致するか（画像が今のコードの描画であること）
2. 敵の描かれた画素（敵を消した描画との差分）のうち、クリックするとその敵が選ばれる画素の割合と、
   選択範囲（当たり判定+6px）のうち敵が描かれていない画素の割合
3. 実際のプレイ（壁あり）でゲート1に着いたとき、E02 が見えて選べる時間（壁に飲まれるまで）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(os.path.dirname(HERE))
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, GAME); sys.path.insert(0, os.path.join(GAME, "tests")); os.chdir(GAME)
import pygame  # noqa: E402
from test_gameplay import DT, STAGE_1, InputState  # noqa: E402
import stage1_bot  # noqa: E402
from systems.targeting import find_target, is_targetable, pick_rect  # noqa: E402
from systems.world import World  # noqa: E402

pygame.init(); pygame.display.set_mode((960, 540))
GL, GR, _ = stage1_bot.gates(STAGE_1)["GATE1"]
lines = []


def log(s=""):
    print(s); lines.append(s)


def world_like_shot(t=2.0):
    """shots.py の frame(STAGE_1, gl-24, t=2.0, mouse_on="E03") と同じ手順。"""
    w = World(STAGE_1, with_graphics=True)
    w.wall.paused = True; w.wall.segments[0].front_x = -1e5
    p = w.player; p.rect.x = GL - 24; p.rect.bottom = 422.0
    inp = InputState()
    for _ in range(int(t / DT)):
        e = next(e for e in w.enemies if e.enemy_id == "E03")
        inp.mouse_pos = w.camera.to_screen(*e.hurtbox.center)
        w.update(DT, inp); inp.clear_edges()
    return w


w = world_like_shot()
s_full = pygame.Surface((960, 540)); w.draw(s_full)

# 1. 画像との一致（注記の枠・ラベルの外側）
img = pygame.image.load(os.path.join(HERE, "gate1_targets.png")).convert()
same = diff = 0
diff_px = []
annot = []
for eid in ("E02", "E03"):
    e = next(e for e in w.enemies if e.enemy_id == eid)
    r = e.hurtbox.move(-w.camera.x, -w.camera.y).inflate(16, 30)
    annot += [r.inflate(6, 6), pygame.Rect(0, int(r.y) - 44, 960, 40)]   # 枠と、その上のラベル
annot += [pygame.Rect(int(GL - w.camera.x) - 3, 0, int(GR - GL) + 6, 428), pygame.Rect(0, 0, 960, 100)]
for y in range(0, 540, 2):
    for x in range(0, 960, 2):
        if any(a.collidepoint(x, y) for a in annot):
            continue
        if img.get_at((x, y))[:3] == s_full.get_at((x, y))[:3]:
            same += 1
        else:
            diff += 1
            diff_px.append((x, y))
log(f"1. gate1_targets.png と、同じ状態を今のコードで描いた画面の一致（注記の外、2px おき）: {same}/{same + diff} 画素")
if diff_px:
    xs = [p[0] for p in diff_px]; ys = [p[1] for p in diff_px]
    log(f"   一致しない画素の範囲: x {min(xs)}〜{max(xs)}, y {min(ys)}〜{max(ys)}")
log(f"   カーソル下の敵（輪郭が光る敵）: {w.hover_target.enemy_id if w.hover_target else None}")

# 2. 描画と選択範囲の対応（敵の体だけ: 背後の光・縁取り・頭上の印・カーソルの輪郭を消して描いた差分）
import config  # noqa: E402
vis_saved = dict(config.VISIBILITY)
config.VISIBILITY.update(enemy_halo_alpha=0, enemy_rim_width=0, target_marker=False)
hover_saved = w.hover_target
w.hover_target = None
s_body = pygame.Surface((960, 540)); w.draw(s_body)
saved = w.enemies
w.enemies = []
s_none = pygame.Surface((960, 540)); w.draw(s_none)
w.enemies = saved
config.VISIBILITY.clear(); config.VISIBILITY.update(vis_saved)
w.hover_target = hover_saved
overlay = s_full.copy()
tint = pygame.Surface((960, 540), pygame.SRCALPHA)
for eid, col in (("E02", (255, 220, 0)), ("E03", (0, 255, 120))):
    e = next(e for e in w.enemies if e.enemy_id == eid)
    pr = pick_rect(e)
    area = pr.move(-w.camera.x, -w.camera.y)
    drawn = hit = pick_px = pick_drawn = 0
    box = pygame.Rect(area.inflate(60, 60)).clip(pygame.Rect(0, 0, 960, 540))
    for y in range(box.top, box.bottom):
        for x in range(box.left, box.right):
            is_drawn = s_body.get_at((x, y))[:3] != s_none.get_at((x, y))[:3]
            sel = find_target(w.enemies, w.camera, w.camera.to_world(x + 0.5, y + 0.5))
            if is_drawn:
                drawn += 1
                hit += sel is e
            if sel is e:
                pick_px += 1
                pick_drawn += is_drawn
                tint.set_at((x, y), (*col, 110))
    log(f"2. {eid}: 敵の体の画素 {drawn} のうち、クリックで {eid} が選ばれる画素 {hit}（{hit / max(1, drawn):.0%}）")
    log(f"   選択範囲（当たり判定 {e.hurtbox.w:.0f}×{e.hurtbox.h:.0f} + 両側6px）{pick_px} 画素のうち、体が描かれている画素 {pick_drawn}"
        f"（{pick_drawn / max(1, pick_px):.0%}）")
    log(f"   画面内に完全に表示: {w.camera.view_rect.contains(e.hurtbox)} / is_targetable: {is_targetable(e, w.camera)} / "
        f"中心をクリック→ {find_target(w.enemies, w.camera, e.hurtbox.center).enemy_id}")
overlay.blit(tint, (0, 0))
big = pygame.transform.scale_by(overlay.subsurface((0, 300, 960, 160)), 2)
pygame.image.save(big, os.path.join(HERE, "gate1_pick_overlay.png"))
log("   → gate1_pick_overlay.png（黄: E02 を選ぶ範囲 / 緑: E03 を選ぶ範囲、下半分を2倍）")

# 3. 実際のプレイでの E02 の見える時間
log("3. 実際のプレイ（壁あり、テレポートなしでゲート1まで走り、そこで待つ）で E02 を選べる時間")
for ws in (-600.0, -450.0):
    for dash in (False, True):
        r0 = stage1_bot.play(STAGE_1, policy="none", dash=dash, wall_start=ws, max_time=30)
        arr = r0.arrive["GATE1"][0]
        wv = World(STAGE_1, with_graphics=False)
        r = stage1_bot.play(STAGE_1, policy="none", dash=dash, wall_start=ws, max_time=arr)
        wv = r.world
        inp = InputState()
        t_vis = None
        t = 0.0
        while wv.state == "playing" and t < 5:
            e2 = next((e for e in wv.enemies if e.enemy_id == "E02"), None)
            ok = e2 is not None and find_target(wv.enemies, wv.camera, e2.hurtbox.center) is e2
            if not ok and t_vis is None:
                t_vis = t
                break
            wv.update(DT, inp); inp.clear_edges(); t += DT
        e3_ok = True
        log(f"   壁 {int(ws)} / {'ダッシュあり' if dash else 'ダッシュなし'}: ゲート1到着 {arr:.2f}秒、"
            f"E02 を選べるのは到着から {f'{t_vis:.2f}秒' if t_vis is not None else '5秒以上'} まで"
            f"（その後は壁に飲まれて消える）、E03 は壁に飲まれるまで選べる")

# 壁ありでゲート1に着いた直後の画面（-600 / -450、ダッシュなし、到着から 1.0 秒）
shots = []
for ws in (-600.0, -450.0):
    r0 = stage1_bot.play(STAGE_1, policy="none", dash=False, wall_start=ws, max_time=30)
    arr = r0.arrive["GATE1"][0]
    r = stage1_bot.play(STAGE_1, policy="none", dash=False, wall_start=ws, max_time=arr + 1.0, with_graphics=True)
    s = pygame.Surface((960, 540)); r.world.draw(s)
    from ui import fonts
    txt = fonts.get_font(18, True).render(f"壁の開始 {int(ws)} / ゲート1到着から1.0秒（ダッシュなし・壁あり）", True, (255, 255, 255))
    bg = pygame.Surface((txt.get_width() + 14, txt.get_height() + 8), pygame.SRCALPHA); bg.fill((0, 0, 0, 180))
    s.blit(bg, (8, 8)); s.blit(txt, (15, 12))
    shots.append(s)
out = pygame.Surface((960 * 2 + 8, 540)); out.fill((255, 255, 255))
out.blit(shots[0], (0, 0)); out.blit(shots[1], (968, 0))
pygame.image.save(out, os.path.join(HERE, "gate1_e02_window.png"))
log("   → gate1_e02_window.png")

with open(os.path.join(HERE, "verify_gate1_targets.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
