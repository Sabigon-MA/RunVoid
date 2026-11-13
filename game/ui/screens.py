"""タイトル・ポーズ・死亡・クリア画面（v2.0: キャラクター選択画面は廃止）。

各画面は handle_event() でアクション文字列（または (アクション, 値)）を返し、
画面遷移の判断は main.Game が行う。
"""
from __future__ import annotations

import math

import pygame

import config
from systems.display import MODE_LABELS, PIXEL_PERFECT
from ui.hud import format_time
from ui.widgets import Menu, draw_panel, draw_text, vertical_buttons

CONTROLS_TEXT = [
    ("A / D", "左右移動"),
    ("Space", "ジャンプ（空中でもう一度: 二段）"),
    ("Shift", "ダッシュ（空中は着地まで1回）"),
    ("S + Space", "一方通行足場から降下"),
    ("左クリック", "敵と位置を入れ替える"),
    ("Esc", "ポーズ"),
    ("F8", "表示切替（整数倍 / 全体）"),
]


class TitleScreen:
    def __init__(self, background):
        self.background = background
        self.time = 0.0
        W = config.SCREEN_WIDTH
        self.menu = Menu(vertical_buttons([("ゲーム開始", "start"), ("終了", "quit")],
                                          W // 2 - 200, 300, width=260))

    def handle_event(self, event):
        return self.menu.handle_event(event)

    def update(self, dt):
        self.time += dt
        self.background.update(dt)

    def draw(self, surface):
        W, H = surface.get_size()
        self.background.draw(surface, self.time * 40)
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        surface.blit(shade, (0, 0))
        # 迫る壁の気配
        glow_w = int(70 + 20 * math.sin(self.time * 2))
        edge = pygame.Surface((glow_w, H), pygame.SRCALPHA)
        for i in range(glow_w):
            pygame.draw.line(edge, (160, 10, 16, int(200 * (1 - i / glow_w))), (i, 0), (i, H))
        surface.blit(edge, (0, 0))

        draw_text(surface, "終焉を背に", 72, (W // 2, 90), (235, 220, 210), anchor="midtop", bold=True)
        draw_text(surface, "- PROTOTYPE : 黄昏の廃王国 -", 20, (W // 2, 182),
                  config.COLORS["ui_dim"], anchor="midtop")
        draw_text(surface, "武器はない。敵をクリックして位置を入れ替え、迫る追跡壁から逃げ切れ。", 16,
                  (W // 2, 220), config.COLORS["ui_text"], anchor="midtop")
        self.menu.draw(surface)

        # 操作説明
        panel = pygame.Rect(W // 2 + 20, 270, 330, 230)
        draw_panel(surface, panel, 170, border=(80, 60, 64))
        draw_text(surface, "操作説明", 18, (panel.left + 16, panel.top + 10), bold=True)
        for i, (key, desc) in enumerate(CONTROLS_TEXT):
            y = panel.top + 42 + i * 26
            draw_text(surface, key, 15, (panel.left + 16, y), config.COLORS["ui_warn"])
            draw_text(surface, desc, 15, (panel.left + 120, y))
        draw_text(surface, "W/S・↑↓で選択  Enterで決定", 14, (W // 2 - 200, 430),
                  config.COLORS["ui_dim"], anchor="midtop")


class OverlayScreen:
    """プレイ画面の上に重ねるメニュー（ポーズ・死亡・クリア）。"""

    def __init__(self, title: str, lines: list[str], buttons: list[tuple[str, str]],
                 title_color=None, shade=150, delay: float = 0.0):
        self.title = title
        self.lines = lines
        self.title_color = title_color or config.COLORS["ui_text"]
        self.shade = shade
        self.time = 0.0
        self.delay = delay   # 誤操作防止: 表示直後は入力を受け付けない
        W = config.SCREEN_WIDTH
        top = 250 + max(0, len(lines) - 3) * 10
        self.menu = Menu(vertical_buttons(buttons, W // 2, top + 20, width=300))

    def handle_event(self, event):
        if self.time < self.delay:
            return None
        return self.menu.handle_event(event)

    def update(self, dt):
        self.time += dt

    def draw(self, surface):
        W, H = surface.get_size()
        fade = min(1.0, self.time / 0.6) if self.delay > 0 else 1.0
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, int(self.shade * fade)))
        surface.blit(shade, (0, 0))
        draw_text(surface, self.title, 64, (W // 2, 70), self.title_color, anchor="midtop", bold=True)
        for i, line in enumerate(self.lines):
            draw_text(surface, line, 20, (W // 2, 160 + i * 30), anchor="midtop")
        if self.time >= self.delay:
            self.menu.draw(surface)


DEATH_CAUSES = {"wall": "追跡壁に飲み込まれた", "hp": "力尽きた", "fall": "奈落へ落ちた"}


def make_pause_screen(display_mode: str = PIXEL_PERFECT) -> OverlayScreen:
    label = f"表示: {MODE_LABELS.get(display_mode, display_mode)}"
    screen = OverlayScreen("PAUSE", ["F8 でも表示を切り替えられます"],
                           [("再開", "resume"), (label, "display"), ("リトライ", "retry"),
                            ("タイトルへ戻る", "title")])
    return screen


def make_death_screen(world) -> OverlayScreen:
    lines = [
        DEATH_CAUSES.get(world.death_cause, ""),
        f"到達距離  {int(world.max_x)} / {int(world.stage.goal_x)} px",
        f"生存時間  {format_time(world.elapsed)}",
        f"テレポート  {world.teleport.count} 回",
    ]
    return OverlayScreen("YOU DIED", lines, [("リトライ", "retry"), ("タイトルへ戻る", "title")],
                         title_color=(200, 30, 36), shade=170, delay=0.6)


def make_clear_screen(world) -> OverlayScreen:
    lines = [
        f"クリア時間  {format_time(world.elapsed)}",
        f"テレポート  {world.teleport.count} 回",
    ]
    return OverlayScreen("PROTOTYPE CLEAR", lines, [("もう一度プレイ", "retry"), ("タイトルへ戻る", "title")],
                         title_color=(255, 210, 140), shade=160, delay=0.6)
