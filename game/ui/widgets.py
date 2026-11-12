"""メニュー用の部品（ボタン・テキスト描画・キーボード/マウス操作できるメニュー）。"""
from __future__ import annotations

import pygame

import config
from ui.fonts import get_font


def draw_text(surface, text, size, pos, color=None, anchor="topleft", bold=False, shadow=True):
    font = get_font(size, bold)
    color = color or config.COLORS["ui_text"]
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(text, True, (0, 0, 0))
        surface.blit(sh, rect.move(2, 2))
    surface.blit(img, rect)
    return rect


def draw_panel(surface, rect, alpha=200, border=None):
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    r, g, b = config.COLORS["ui_panel"]
    panel.fill((r, g, b, alpha))
    surface.blit(panel, rect.topleft)
    if border:
        pygame.draw.rect(surface, border, rect, 1)


class Button:
    def __init__(self, label: str, action, rect: pygame.Rect, size: int = 24):
        self.label = label
        self.action = action
        self.rect = pygame.Rect(rect)
        self.size = size

    def draw(self, surface, selected: bool) -> None:
        accent = config.COLORS["ui_accent"]
        draw_panel(surface, self.rect, 210 if selected else 150,
                   border=accent if selected else (70, 60, 64))
        if selected:
            pygame.draw.rect(surface, accent, (self.rect.left, self.rect.top, 4, self.rect.height))
        draw_text(surface, self.label, self.size, self.rect.center,
                  config.COLORS["ui_text"] if selected else config.COLORS["ui_dim"], anchor="center")


class Menu:
    """縦並びボタン。W/S・↑↓で選択、Enter/Space で決定、マウスでも操作可能。"""

    def __init__(self, buttons: list[Button]):
        self.buttons = buttons
        self.selected = 0

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_w, pygame.K_UP):
                self.selected = (self.selected - 1) % len(self.buttons)
            elif event.key in (pygame.K_s, pygame.K_DOWN):
                self.selected = (self.selected + 1) % len(self.buttons)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.buttons[self.selected].action
        elif event.type == pygame.MOUSEMOTION:
            for i, b in enumerate(self.buttons):
                if b.rect.collidepoint(event.pos):
                    self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, b in enumerate(self.buttons):
                if b.rect.collidepoint(event.pos):
                    self.selected = i
                    return b.action
        return None

    def draw(self, surface) -> None:
        for i, b in enumerate(self.buttons):
            b.draw(surface, i == self.selected)


def vertical_buttons(labels_actions, center_x, top, width=280, height=46, gap=12, size=24):
    buttons = []
    for i, (label, action) in enumerate(labels_actions):
        rect = pygame.Rect(0, 0, width, height)
        rect.midtop = (center_x, top + i * (height + gap))
        buttons.append(Button(label, action, rect, size))
    return buttons
