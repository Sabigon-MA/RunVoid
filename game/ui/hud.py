"""プレイ中の HUD（HP・ダッシュ・テレポート・壁との距離・経過時間・ボスHP・照準）。"""
from __future__ import annotations

import math

import pygame

import config
from ui.widgets import draw_panel, draw_text


def format_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


def _bar(surface, x, y, w, h, ratio, color, back=(30, 24, 28)):
    pygame.draw.rect(surface, back, (x, y, w, h))
    pygame.draw.rect(surface, color, (x, y, int(w * max(0.0, min(1.0, ratio))), h))


class HUD:
    def __init__(self):
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, surface: pygame.Surface, world) -> None:
        player = world.player
        W, H = surface.get_size()
        c = config.COLORS

        # --- 左上: HP・ダッシュ・テレポート ---
        draw_panel(surface, pygame.Rect(10, 10, 300, 112), 150)
        draw_text(surface, player.name, 20, (20, 16), c["ui_text"], bold=True)
        max_hp = player.stats["max_hp"]
        for i in range(max_hp):
            col = c["hp"] if i < player.hp else c["hp_empty"]
            cx, cy = 28 + i * 24, 56
            pygame.draw.polygon(surface, col, [(cx, cy - 9), (cx + 9, cy), (cx, cy + 9), (cx - 9, cy)])
        # ダッシュ（空中は使用権がある場合のみ）
        dash_ratio = 1.0 - player.dash_cooldown / player.stats["dash_cooldown"]
        has_charge = player.on_ground or player.air_dashes_remaining > 0
        dash_ready = dash_ratio >= 1.0 and has_charge
        draw_text(surface, "ダッシュ", 14, (180, 48), c["ui_text"] if dash_ready else c["ui_dim"])
        _bar(surface, 240, 54, 60, 6, dash_ratio if has_charge else 0, (220, 200, 160))
        self._draw_teleport_status(surface, world, 20, 76)

        # --- 右上: 経過時間・進行度 ---
        draw_panel(surface, pygame.Rect(W - 230, 10, 220, 80), 150)
        draw_text(surface, f"TIME  {format_time(world.elapsed)}", 18, (W - 220, 16))
        draw_text(surface, f"テレポート  {world.teleport.count} 回", 16, (W - 220, 42))
        progress = min(1.0, player.rect.right / world.stage.goal_x)
        _bar(surface, W - 220, 70, 200, 6, progress, (230, 190, 120))

        # --- 下中央: ボスHP ---
        boss = world.active_boss
        if boss is not None and boss.alive:
            bw = 420
            bx = (W - bw) // 2
            draw_panel(surface, pygame.Rect(bx - 10, H - 58, bw + 20, 46), 160)
            draw_text(surface, getattr(boss, "display_name", "BOSS"), 16, (bx, H - 54), c["ui_text"], bold=True)
            _bar(surface, bx, H - 30, bw, 10, boss.hp / boss.max_hp, (200, 60, 200))

        # --- 上中央: 追跡壁との距離 ---
        dist = max(0.0, world.wall_distance)
        if dist < config.WALL_DANGER_DISTANCE:
            col = c["ui_accent"]
        elif dist < config.WALL_WARNING_DISTANCE:
            col = c["ui_warn"]
        else:
            col = c["ui_text"]
        draw_text(surface, f"追跡壁まで {int(dist)} px", 18, (W // 2, 16), col, anchor="midtop", bold=True)

        # --- 壁が画面外のとき: 左端に距離表示と警告 ---
        if not world.wall_on_screen:
            self._draw_offscreen_indicator(surface, dist)
        elif dist < config.WALL_WARNING_DISTANCE:
            self._draw_warning_edge(surface, dist)

        self._draw_reticle(surface, world)

    def _draw_teleport_status(self, surface, world, x, y):
        c = config.COLORS
        tp = world.teleport
        ready = tp.ready
        if ready:
            pulse = 0.6 + 0.4 * math.sin(self.time * 5)
            r, g, b = c["teleport"]
            col = (int(r + (255 - r) * pulse * 0.3), int(g + (255 - g) * pulse * 0.3), int(b + (255 - b) * pulse * 0.3))
            label = "テレポート  READY"
        else:
            col = c["ui_dim"]
            label = f"テレポート  {tp.cooldown_remaining:.1f}s"
        draw_text(surface, label, 16, (x, y), col, bold=ready)
        _bar(surface, x, y + 26, 280, 8, tp.ready_ratio, c["teleport"] if ready else c["teleport_dim"])
        if tp.feedback_timer > 0 and tp.last_result is not None and not tp.last_result.ok:
            msg = {"blocked": "交換先に安全な位置がない", "cooldown": "クールダウン中"}.get(
                tp.last_result.reason, "")
            if msg:
                draw_text(surface, msg, 14, (x + 150, y + 2), c["ui_accent"])

    def _draw_reticle(self, surface, world):
        """マウスカーソルの代わりに描く照準。テレポート可能な敵の上では専用表示になる。"""
        if world.state != "playing":
            return
        c = config.COLORS
        mx, my = world.mouse_screen
        target = world.hover_target
        if target is None:
            col = (220, 210, 200)
            pygame.draw.circle(surface, col, (mx, my), 6, 1)
            pygame.draw.line(surface, col, (mx - 10, my), (mx - 4, my))
            pygame.draw.line(surface, col, (mx + 4, my), (mx + 10, my))
            pygame.draw.line(surface, col, (mx, my - 10), (mx, my - 4))
            pygame.draw.line(surface, col, (mx, my + 4), (mx, my + 10))
            return
        ready = world.teleport.ready
        col = c["teleport"] if ready else c["teleport_dim"]
        spin = self.time * (4.0 if ready else 1.0)
        rad = 14 + (2 * math.sin(self.time * 10) if ready else 0)
        for k in range(4):
            a = spin + k * math.pi / 2
            p1 = (mx + math.cos(a) * rad, my + math.sin(a) * rad)
            p2 = (mx + math.cos(a + 0.6) * rad, my + math.sin(a + 0.6) * rad)
            pygame.draw.line(surface, col, p1, p2, 3)
        pygame.draw.circle(surface, col, (mx, my), 3)
        if not ready:
            draw_text(surface, f"{world.teleport.cooldown_remaining:.1f}", 13, (mx + 16, my + 10),
                      c["ui_dim"])

    def _draw_offscreen_indicator(self, surface, dist):
        W, H = surface.get_size()
        c = config.COLORS
        danger = dist < config.WALL_WARNING_DISTANCE
        pulse = 0.5 + 0.5 * math.sin(self.time * (14 if dist < config.WALL_DANGER_DISTANCE else 7))
        col = c["ui_accent"] if danger else (200, 120, 110)
        cy = H // 2
        if danger:
            self._draw_warning_edge(surface, dist)
        pygame.draw.polygon(surface, col, [(8, cy), (26, cy - 14), (26, cy + 14)])
        draw_panel(surface, pygame.Rect(30, cy - 22, 150, 44), 170)
        draw_text(surface, "追跡壁", 14, (38, cy - 18), col)
        draw_text(surface, f"{int(dist)} px", 18, (38, cy - 1), col, bold=True)
        if danger and pulse > 0.5:
            draw_text(surface, "WARNING", 16, (30, cy + 26), c["ui_accent"], bold=True)

    def _draw_warning_edge(self, surface, dist):
        W, H = surface.get_size()
        strength = 1.0 - dist / config.WALL_WARNING_DISTANCE
        pulse = 0.6 + 0.4 * math.sin(self.time * 10)
        edge = pygame.Surface((60, H), pygame.SRCALPHA)
        for i in range(60):
            a = int(140 * strength * pulse * (1 - i / 60))
            pygame.draw.line(edge, (220, 20, 20, a), (i, 0), (i, H))
        surface.blit(edge, (0, 0))
