"""ステージの仮グラフィック描画（背景・地形・ゴール）。

外部画像を使わず pygame の描画機能だけで生成する。
重い描画は初期化時にサーフェスへ焼き込み、毎フレームは blit のみ行う。
"""
from __future__ import annotations

import logging
import math
import random

import pygame

import config
from stages.background import BackgroundAssetError, BackgroundConfig, build_background


def _vertical_gradient(w: int, h: int, stops: list[tuple[float, tuple[int, int, int]]]) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                color = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
                pygame.draw.line(surf, color, (0, y), (w, y))
                break
    return surf


class ParallaxLayer:
    def __init__(self, surface: pygame.Surface, factor: float, y: int = 0):
        self.surface = surface
        self.factor = factor
        self.y = y

    def draw(self, target: pygame.Surface, camera_x: float) -> None:
        w = self.surface.get_width()
        offset = -(camera_x * self.factor) % w
        x = offset - w
        tw = target.get_width()
        while x < tw:
            target.blit(self.surface, (x, self.y))
            x += w


class TwilightRuinsBackground:
    """ステージ1「黄昏の廃王国」: 荒れた平原、枯草、遠くの廃城。"""

    def __init__(self, view_w: int, view_h: int, seed: int = 7):
        self.view_w, self.view_h = view_w, view_h
        rng = random.Random(seed)
        self.sky = _vertical_gradient(view_w, view_h, [
            (0.0, (28, 16, 36)),
            (0.45, (92, 38, 48)),
            (0.72, (178, 82, 48)),
            (1.0, (70, 34, 34)),
        ])
        # 沈む太陽
        sun = pygame.Surface((view_w, view_h), pygame.SRCALPHA)
        for r in range(140, 0, -10):
            a = int(10 + (140 - r) * 0.35)
            pygame.draw.circle(sun, (255, 140, 70, a), (int(view_w * 0.72), int(view_h * 0.62)), r)
        self.sky.blit(sun, (0, 0))
        self.layers = [
            ParallaxLayer(self._castle_layer(1600, view_h, rng), 0.08),
            ParallaxLayer(self._hill_layer(1400, view_h, rng, (52, 26, 34), 330, 40), 0.2),
            ParallaxLayer(self._hill_layer(1200, view_h, rng, (36, 20, 26), 375, 28), 0.4),
            ParallaxLayer(self._grass_layer(1000, view_h, rng), 0.65),
        ]
        self.ash = [(rng.uniform(0, view_w), rng.uniform(0, view_h), rng.uniform(8, 25),
                     rng.uniform(0, math.tau)) for _ in range(40)]
        self.time = 0.0

    @staticmethod
    def _castle_layer(w, h, rng):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        color = (58, 30, 42)
        base = 360
        x = 300
        # 廃城のシルエット（崩れた塔と城壁）
        pygame.draw.rect(surf, color, (x, base - 60, 360, 60))
        for i, (tx, th, tw) in enumerate([(x + 10, 150, 40), (x + 120, 210, 52),
                                          (x + 230, 120, 36), (x + 300, 175, 44)]):
            pygame.draw.rect(surf, color, (tx, base - th, tw, th))
            # 崩れた頂部
            pts = [(tx, base - th)]
            for k in range(5):
                pts.append((tx + tw * (k + 0.5) / 5, base - th - rng.randint(0, 22)))
            pts.append((tx + tw, base - th))
            pygame.draw.polygon(surf, color, pts)
            # 窓
            pygame.draw.rect(surf, (120, 50, 40), (tx + tw // 2 - 3, base - th + 30, 6, 12))
        for k in range(18):  # 城壁の狭間
            pygame.draw.rect(surf, color, (x + k * 20, base - 72, 10, 12))
        # 遠くの小さな廃墟
        for _ in range(4):
            rx = rng.randint(800, w - 100)
            rh = rng.randint(30, 80)
            pygame.draw.rect(surf, color, (rx, base - rh, rng.randint(14, 30), rh))
        pygame.draw.rect(surf, color, (0, base, w, h - base))
        return surf

    @staticmethod
    def _hill_layer(w, h, rng, color, base, amp):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pts = [(0, h)]
        phase1, phase2 = rng.uniform(0, 6), rng.uniform(0, 6)
        for x in range(0, w + 1, 20):
            t = x / w * math.tau
            y = base - amp * (0.6 * math.sin(t * 2 + phase1) + 0.4 * math.sin(t * 5 + phase2))
            pts.append((x, y))
        pts.append((w, h))
        pygame.draw.polygon(surf, color, pts)
        # 枯れ木
        for _ in range(3):
            tx = rng.randint(40, w - 40)
            ty = base + 10
            pygame.draw.line(surf, color, (tx, ty), (tx, ty - 50), 3)
            pygame.draw.line(surf, color, (tx, ty - 35), (tx - 16, ty - 55), 2)
            pygame.draw.line(surf, color, (tx, ty - 28), (tx + 14, ty - 46), 2)
        return surf

    @staticmethod
    def _grass_layer(w, h, rng):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = 418
        # 地面より下は奈落として暗く落とし込む（穴が足場と見分けられるように）
        for y in range(base, h):
            k = min(1.0, (y - base) / 40)
            col = (int(46 * (1 - k) + 4 * k), int(28 * (1 - k) + 2 * k), int(26 * (1 - k) + 4 * k))
            pygame.draw.line(surf, col, (0, y), (w, y))
        for _ in range(260):
            x = rng.uniform(0, w)
            length = rng.uniform(8, 26)
            lean = rng.uniform(-6, 6)
            pygame.draw.line(surf, (86, 58, 40), (x, base + 2), (x + lean, base - length), 1)
        return surf

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, surface: pygame.Surface, camera_x: float, camera_y: float = 0.0) -> None:
        surface.blit(self.sky, (0, 0))
        for layer in self.layers:
            layer.draw(surface, camera_x)
        # 舞い散る灰
        t = self.time
        for (x, y, spd, ph) in self.ash:
            ax = (x - camera_x * 0.3 + math.sin(t + ph) * 12) % self.view_w
            ay = (y + t * spd) % self.view_h
            pygame.draw.rect(surface, (190, 150, 130), (ax, ay, 2, 2))


BACKGROUNDS = {"twilight_ruins": TwilightRuinsBackground}


def make_background(theme: str, view_w: int, view_h: int, background: BackgroundConfig | None = None):
    """背景を作る。画像背景の設定があればそれを使い、画像の欠落・破損時だけ手続き背景へ戻す。"""
    if background is not None:
        try:
            return build_background(background, view_w, view_h)
        except BackgroundAssetError as exc:
            logging.getLogger("runvoid.background").warning(
                "%s -> 手続き背景 '%s' で続行します", exc, theme)
    cls = BACKGROUNDS.get(theme, TwilightRuinsBackground)
    return cls(view_w, view_h)


def find_pits(rects, world_width: float, view_h: int) -> list[tuple[int, int, int]]:
    """画面下端まで届く固体地形の切れ目（= 穴）を (左x, 右x, 上端y) で返す。描画専用。

    上端は両隣の地面の上面のうち高い方（小さい y）。ステージ両端の外側は穴として扱わない。
    v3.0: 上面が画面の高さより下にある地形（地下の床・壁）は地上の床として数えない（v2.5 には該当なし）。
    """
    floor = sorted((r for r in rects if r.bottom >= view_h and r.top < view_h), key=lambda r: r.left)
    pits = []
    covered = 0
    prev = None
    for r in floor:
        if r.left > covered and prev is not None:
            pits.append((int(covered), int(r.left), int(min(prev.top, r.top))))
        if r.right > covered:
            covered, prev = r.right, r
    return [p for p in pits if 0 < p[0] < p[1] < world_width]


PIT_DEATH, PIT_ENTRANCE = "death", "entrance"


def classify_pits(rects, pits, view_h: int) -> list[str]:
    """v3.0: 穴ごとに「落とし穴（下に何もない＝落下死）」か「地下への入口（下に地下の床がある）」かを返す。

    下に上面が画面の高さ以上の地形（地下の床・階段）が水平に重なっていれば入口。描画とテスト用。
    """
    kinds = []
    for x0, x1, _top in pits:
        below = any(r.top >= view_h and r.left < x1 and r.right > x0 for r in rects)
        kinds.append(PIT_ENTRANCE if below else PIT_DEATH)
    return kinds


def _gate_floor_y(rect, rects, view_h: int) -> float:
    """城門の両隣の地面の上面（門の開口部の床の高さ）。隣に地面がなければ画面下端から 118px 上。"""
    tops = [o.top for o in rects if o is not rect and o.bottom >= view_h
            and (abs(o.right - rect.left) < 1 or abs(o.left - rect.right) < 1)]
    return min(tops) if tops else view_h - 118


class SealedGateArt:
    """封鎖された城門（style="sealed_gate"）。v2.5、描画のみ。

    崩落した城門（石積み・亀裂・瓦礫で埋まったアーチ・下ろされた落とし格子）を、異星の侵食
    （青緑に光る脈と結晶、アーチを封じる紋章）が覆う。石の部分は当たり判定の矩形からはみ出さない
    （見えている石の輪郭＝通れない範囲）。矩形の外に出るのは細い光の筋だけ。
    重い描画は初期化時に焼き込み、毎フレームは2枚の blit と脈打つ光の不透明度の変更だけ。
    """

    OVERHANG = 12   # 光の筋が矩形の外へ出てよい幅（片側）

    def __init__(self, rect, view_h: int, floor_y: float, seed: int = 0):
        self.rect = pygame.Rect(int(rect.x), int(rect.y), int(rect.w), int(rect.h))
        rng = random.Random(seed)
        c = config.COLORS
        ov = self.OVERHANG
        w = self.rect.w
        h = max(1, min(self.rect.bottom, view_h) - self.rect.y)
        fy = int(floor_y - self.rect.y)                 # 床の高さ（ローカル座標）
        self.origin = (self.rect.x - ov, self.rect.y)
        self.stone = pygame.Surface((w + ov * 2, h), pygame.SRCALPHA)
        self.glow = pygame.Surface((w + ov * 2, h), pygame.SRCALPHA)
        st, gl = self.stone, self.glow
        x0, x1 = ov, ov + w                             # 矩形の左右（ローカル）

        # --- 石積み -----------------------------------------------------
        pygame.draw.rect(st, c["gate_mortar"], (x0, 0, w, h))
        course = 22
        for row, y in enumerate(range(0, h, course)):
            x = x0 - (rng.randint(4, 16) if row % 2 else 0)
            while x < x1:
                bw = rng.randint(18, 34)
                v = rng.randint(-8, 10)
                col = tuple(max(0, min(255, k + v)) for k in c["gate_stone"])
                blk = pygame.Rect(x + 1, y + 1, bw - 2, course - 2).clip(pygame.Rect(x0, 0, w, h))
                if blk.w > 0:
                    pygame.draw.rect(st, col, blk)
                    pygame.draw.line(st, tuple(min(255, k + 14) for k in col), blk.topleft, blk.topright)
                x += bw
        # 床より下は隣の地面と同じ描き方にする（門が地面の上に立っていて、床が途切れていないように見せる）
        if fy < h:
            pygame.draw.rect(st, c["ground"], (x0, fy, w, h - fy))
            pygame.draw.rect(st, c["ground_top"], (x0, fy, w, 6))
            for _ in range(max(1, w // 30)):
                pygame.draw.rect(st, (44, 34, 36), (rng.randint(x0, x1 - 16), rng.randint(fy + 14, max(fy + 15, h - 10)),
                                                    rng.randint(8, 16), rng.randint(4, 8)))

        # --- 崩落: 全幅の断裂（下側の石がずれ落ちている）と、上部の亀裂・欠け ------------
        sy = rng.randint(max(30, fy - 330), max(31, fy - 250))
        frac = [(x0, sy)]
        for x in range(x0 + 8, x1, 8):
            frac.append((x, sy + rng.randint(-5, 5)))
        frac.append((x1 - 1, sy + rng.randint(-3, 3)))
        for (fx, fy_) in frac[1:-1:2]:   # ずれた石（少し傾いた石塊）
            bw = rng.randint(12, 20)
            tilt = rng.randint(-3, 3)
            pygame.draw.polygon(st, tuple(min(255, k + 8) for k in c["gate_stone"]),
                                [(fx, fy_ + 3), (min(x1 - 3, fx + bw), fy_ + 3 + tilt),
                                 (min(x1 - 3, fx + bw), fy_ + 15 + tilt), (fx, fy_ + 15)])
        pygame.draw.lines(st, (8, 5, 8), False, frac, 4)
        pygame.draw.lines(st, (96, 80, 70), False, [(x, y - 3) for x, y in frac], 1)
        # 上部の亀裂と欠け
        for _ in range(3):
            px, py = rng.randint(x0 + 6, x1 - 6), rng.randint(10, max(11, fy - 260))
            pts = [(px, py)]
            for _ in range(rng.randint(4, 7)):
                px = min(x1 - 3, max(x0 + 3, px + rng.randint(-10, 10)))
                py += rng.randint(10, 26)
                pts.append((px, py))
            pygame.draw.lines(st, (12, 8, 10), False, pts, 3)
            pygame.draw.lines(st, (82, 68, 64), False, [(x + 2, y) for x, y in pts], 1)
        for _ in range(3):   # 欠けた石（暗い窪み。輪郭は矩形のまま）
            cx, cy = rng.choice((x0 + 8, x1 - 8)), rng.randint(20, max(21, fy - 220))
            r = rng.randint(6, 11)
            poly = [(cx + math.cos(a) * r * rng.uniform(0.6, 1.2), cy + math.sin(a) * r * rng.uniform(0.6, 1.2))
                    for a in [i * math.tau / 7 for i in range(7)]]
            pygame.draw.polygon(st, (18, 12, 16), poly)

        # --- 城門のアーチ（瓦礫と落とし格子で塞がれている） ----------------------
        aw = max(16, min(w - 18, int(w * 0.6)))   # 幅の4割は石の枠に残す（開口部だけが目立って通路に見えないように）
        ah = min(178, max(60, fy - 40))
        ax0, ax1 = x0 + (w - aw) // 2, x0 + (w - aw) // 2 + aw
        a_top = fy - ah
        arch = pygame.Rect(ax0, a_top, aw, ah)
        pygame.draw.rect(st, c["gate_recess"], (ax0, a_top + aw // 2, aw, ah - aw // 2))
        pygame.draw.ellipse(st, c["gate_recess"], (ax0, a_top, aw, aw))
        # 異星の膜: アーチの開口部を六角格子の膜がふさぐ（暗い通路ではなく「封じられた門」に見せる）。
        # 格子と瓦礫はこの手前に描く
        mem = pygame.Surface((aw, ah), pygame.SRCALPHA)
        mem.fill((*c["gate_vein_dark"], 150))
        hr = 5
        for row, hy in enumerate(range(0, ah + hr, int(hr * 1.5))):
            for hx in range(-hr if row % 2 else 0, aw + hr, int(hr * 1.75)):
                pts = [(hx + math.cos(a) * hr, hy + math.sin(a) * hr)
                       for a in [math.pi / 6 + i * math.pi / 3 for i in range(6)]]
                pygame.draw.polygon(mem, (*c["gate_crystal"], 170), pts, 1)
        mask = pygame.Surface((aw, ah), pygame.SRCALPHA)       # アーチの形に切り抜く（上は半円）
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, aw // 2, aw, ah - aw // 2))
        pygame.draw.ellipse(mask, (255, 255, 255, 255), (0, 0, aw, aw))
        mem.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        st.blit(mem, (ax0, a_top))
        # 迫石（アーチの縁）
        for i in range(9):
            a = math.pi + math.pi * i / 8
            ex = ax0 + aw / 2 + math.cos(a) * (aw / 2 + 2)
            ey = a_top + aw / 2 + math.sin(a) * (aw / 2 + 2)
            pygame.draw.circle(st, c["gate_edge"], (int(ex), int(ey)), 3)
        pygame.draw.line(st, c["gate_edge"], (ax0 - 2, a_top + aw // 2), (ax0 - 2, fy), 3)
        pygame.draw.line(st, c["gate_edge"], (ax1 + 1, a_top + aw // 2), (ax1 + 1, fy), 3)
        # 下ろされた落とし格子（一部が曲がっている）
        iron = c["gate_iron"]
        for bx in range(ax0 + 5, ax1 - 2, 9):
            bend = rng.choice((0, 0, 0, rng.randint(-4, 4)))
            top_y = a_top + aw // 2 - int(math.sqrt(max(0, (aw / 2) ** 2 - (bx - ax0 - aw / 2) ** 2)))
            pygame.draw.line(st, iron, (bx, top_y + 3), (bx + bend, fy), 2)
        for by in range(a_top + aw // 2 + 6, fy, 18):
            pygame.draw.line(st, iron, (ax0 + 2, by), (ax1 - 3, by + rng.randint(-2, 2)), 2)
        # 落ちた楣石（アーチの上部を斜めに塞ぐ折れた石梁）
        ly = a_top + aw // 2 + 8
        slab = [(ax0 - 1, ly), (ax1 + 1, ly + 22), (ax1 + 1, ly + 34), (ax0 - 1, ly + 12)]
        pygame.draw.polygon(st, tuple(min(255, k + 12) for k in c["gate_stone"]), slab)
        pygame.draw.line(st, c["gate_edge"], slab[0], slab[1], 2)
        pygame.draw.line(st, (12, 8, 10), (ax0 + aw // 2, ly + 11), (ax0 + aw // 2 + 4, ly + 24), 2)   # 折れ目
        # 瓦礫の山（アーチの下を埋める）
        for _ in range(34):
            rw, rh = rng.randint(8, min(22, aw)), rng.randint(7, 14)
            rx = rng.randint(ax0, max(ax0, ax1 - rw))
            ry = fy - rh - int(rng.random() ** 1.4 * 100)
            v = rng.randint(-6, 18)
            pygame.draw.rect(st, tuple(max(0, min(255, k + v)) for k in c["gate_stone"]), (rx, ry, rw, rh))
            pygame.draw.line(st, c["gate_edge"], (rx, ry), (rx + rw - 1, ry))
        # 輪郭（左右の縁を明るい石にして背景から切り離す）
        for x, col in ((x0, (16, 10, 12)), (x0 + 1, c["gate_edge"]), (x0 + 2, c["gate_edge"]),
                       (x1 - 1, (16, 10, 12)), (x1 - 2, c["gate_edge"]), (x1 - 3, c["gate_edge"])):
            pygame.draw.line(st, col, (x, 0), (x, min(h, fy + 4)))

        # --- 異星の侵食: 光る脈・結晶・封印の紋章 --------------------------------
        vein, vdark, crystal = c["gate_vein"], c["gate_vein_dark"], c["gate_crystal"]
        self.paths = []
        starts = [(rng.randint(x0 + 4, x1 - 4), fy - 2) for _ in range(3)] + \
                 [(rng.choice((x0 + 2, x1 - 2)), rng.randint(fy - 260, fy - 120)) for _ in range(3)]
        for sx, sy in starts:
            pts = [(sx, sy)]
            x, y = sx, sy
            for _ in range(rng.randint(8, 14)):
                x = min(x1 - 3, max(x0 + 3, x + rng.randint(-9, 9)))
                y -= rng.randint(10, 24)
                if y < 0:
                    break
                pts.append((x, y))
            if len(pts) < 2:
                continue
            self.paths.append(pts)
            pygame.draw.lines(st, vdark, False, pts, 4)
            pygame.draw.lines(gl, (*vein, 70), False, pts, 5)
            pygame.draw.lines(gl, (*vein, 230), False, pts, 1)
            # 分岐と結晶
            for (bx, by) in pts[2::3]:
                d = rng.choice((-1, 1))
                # 結晶は矩形の内側に収める（外にはみ出した石・結晶は足場に見えるため）
                tip = (min(x1 - 2, max(x0 + 1, bx + d * rng.randint(8, 16))), by - rng.randint(6, 16))
                pygame.draw.polygon(st, crystal, [(bx - 2, by), (bx + 2, by), tip])
                pygame.draw.line(gl, (*vein, 200), (bx, by), tip, 1)
        # 矩形の外へ伸びる細い光の筋（足場に見えないよう、石は描かない）
        for _ in range(4):
            side = rng.choice((-1, 1))
            sy = rng.randint(max(0, fy - 330), fy - 30)
            ex = (x0 if side < 0 else x1 - 1)
            pts = [(ex, sy), (ex + side * ov * 0.5, sy - 6), (ex + side * (ov - 2), sy - rng.randint(10, 20))]
            pygame.draw.lines(gl, (*vein, 150), False, pts, 1)
        # 封印の紋章（アーチの中央、主人公の目の高さ付近）と、アーチを横切る障壁の筋
        scx, scy = (ax0 + ax1) // 2, int(a_top + ah * 0.48)
        rad = max(8, min(15, aw // 2 - 4))
        for x in range(ax0 + 3, ax1 - 2, 5):
            pygame.draw.line(gl, (*vein, 46), (x, a_top + aw // 2), (x, fy - 2))
        pygame.draw.circle(gl, (*vein, 60), (scx, scy), rad + 6)
        pygame.draw.circle(gl, (*vein, 235), (scx, scy), rad, 2)
        tri = [(scx + math.cos(a) * (rad - 4), scy + math.sin(a) * (rad - 4))
               for a in (-math.pi / 2, math.pi / 6, math.pi * 5 / 6)]
        pygame.draw.polygon(gl, (*vein, 235), tri, 1)
        pygame.draw.circle(gl, (235, 255, 250, 255), (scx, scy), 2)
        for a in (math.pi, 0.0):
            ex = scx + math.cos(a) * (aw / 2 - 1)
            pygame.draw.line(gl, (*vein, 160), (scx + math.cos(a) * rad, scy), (ex, scy), 1)
        self.sigil = (scx, scy, rad)
        self.phase = rng.uniform(0, math.tau)
        # 不透明な石・結晶は当たり判定の矩形の内側だけに残す（見えている石の輪郭＝通れない範囲）
        st.fill((0, 0, 0, 0), (0, 0, x0, h))
        st.fill((0, 0, 0, 0), (x1, 0, ov, h))

    def draw(self, surface: pygame.Surface, camera, t: float) -> None:
        ox, oy = self.origin[0] - camera.x, self.origin[1] - camera.y
        surface.blit(self.stone, (ox, oy))
        pulse = 0.5 + 0.5 * math.sin(t * 2.4 + self.phase)
        self.glow.set_alpha(int(150 + 105 * pulse))
        surface.blit(self.glow, (ox, oy))
        # 脈を昇る光の粒
        for i, pts in enumerate(self.paths):
            n = len(pts) - 1
            u = (t * 0.9 + i * 0.37) % 1.0 * n
            k = int(u)
            (ax, ay), (bx, by) = pts[k], pts[min(n, k + 1)]
            f = u - k
            px, py = ax + (bx - ax) * f + ox, ay + (by - ay) * f + oy
            pygame.draw.rect(surface, (220, 255, 248), (int(px), int(py), 2, 2))


class CheckpointMarker:
    """v2.5: チェックポイントの目印。壊れた石碑に、異星文明の小さな装置（輪と3本の爪、紋様）が埋め込まれている。

    描画専用で当たり判定はない（地形・敵・テレポートの判定には一切登録しない）。
    未起動: 石碑と暗い装置だけ（核がごくわずかに明滅）。
    起動済み: 核と紋様が淡い青紫に光り、周りにやわらかい光と昇る粒。起動した瞬間は光の柱と地面の輪が広がる。
    乱数は自前の Random を使い、描画時には乱数を使わない（物理・敵の乱数に影響しない）。
    """
    W, H = 44, 60
    FLASH_SECONDS = 0.9

    def __init__(self, x: float, floor_y: float, seed: int = 0):
        c = config.COLORS
        rng = random.Random(seed)
        w, h = self.W, self.H
        self.x, self.floor_y = float(x), float(floor_y)
        self.origin = (round(x) - w // 2, round(floor_y) - h + 2)    # 台座の下端を地面に 2px 埋める
        base = h - 2
        st = pygame.Surface((w, h), pygame.SRCALPHA)
        # 台座（ずれた2段の石）
        pygame.draw.rect(st, c["cp_stone_dark"], (9, base - 7, 26, 7))
        pygame.draw.rect(st, c["cp_stone"], (11, base - 11, 21, 5))
        pygame.draw.line(st, c["cp_edge"], (11, base - 11), (31, base - 11))
        # 石碑本体（上が斜めに折れている）
        x0, x1, foot = 14, 29, base - 11
        body = [(x0, foot), (x0, 14), (x0 + 3, 10), (x0 + 6, 15), (x0 + 9, 8), (x0 + 12, 13), (x1, 18), (x1, foot)]
        pygame.draw.polygon(st, c["cp_stone"], body)
        pygame.draw.line(st, c["cp_edge"], (x0, foot), (x0, 14))                 # 左の縁（光の当たる面）
        pygame.draw.lines(st, c["cp_edge"], False, body[1:7])                    # 折れ口
        pygame.draw.line(st, c["cp_stone_dark"], (x1, 18), (x1, foot))           # 右の影
        for _ in range(3):                                                       # 亀裂
            cx, cy = rng.randint(x0 + 2, x1 - 3), rng.randint(20, foot - 6)
            pygame.draw.line(st, c["cp_stone_dark"], (cx, cy), (cx + rng.randint(-3, 3), cy + rng.randint(3, 7)))
        # 折れた破片（台座の右に転がる）
        pygame.draw.polygon(st, c["cp_stone"], [(31, base - 1), (34, base - 6), (39, base - 5), (40, base - 1)])
        pygame.draw.line(st, c["cp_edge"], (34, base - 6), (39, base - 5))
        # 異星の装置: 輪と3本の爪（石を貫いて食い込む）
        self.core = (21, 27)
        cx, cy = self.core
        for ang in (-150, -30, 90):
            a = math.radians(ang)
            pygame.draw.line(st, c["cp_device"], (cx + math.cos(a) * 5, cy + math.sin(a) * 5),
                             (cx + math.cos(a) * 10, cy + math.sin(a) * 10), 2)
        pygame.draw.circle(st, c["cp_device"], (cx, cy), 6)
        pygame.draw.circle(st, c["cp_stone_dark"], (cx, cy), 3)
        self.stone = st
        # 紋様（装置から石碑の下へ伸びる回路のような線）。未起動・起動済みで色だけ変える
        glyph = [[(cx, cy + 6), (cx, cy + 11), (cx - 4, cy + 14), (cx - 4, foot - 2)],
                 [(cx + 2, cy + 6), (cx + 5, cy + 10), (cx + 5, foot - 4)],
                 [(cx - 1, cy - 6), (cx - 1, cy - 10), (cx + 3, cy - 13)]]
        self.dim = pygame.Surface((w, h), pygame.SRCALPHA)
        self.lit = pygame.Surface((w, h), pygame.SRCALPHA)
        for surf, col, core in ((self.dim, c["cp_dim"], c["cp_dim"]), (self.lit, c["cp_glow"], c["cp_core"])):
            for pts in glyph:
                pygame.draw.lines(surf, col, False, pts)
            pygame.draw.circle(surf, col, (cx, cy), 3)
            pygame.draw.circle(surf, core, (cx, cy), 1)
        # やわらかい光（起動済み）
        r = 30
        self.halo = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        g = c["cp_glow"]
        for i in range(r, 0, -1):
            pygame.draw.circle(self.halo, (*g, int(70 * (1 - i / r) ** 1.8)), (r, r), i)
        self.halo_r = r

    def draw(self, surface: pygame.Surface, camera, t: float, lit: bool, age: float) -> None:
        ox, oy = self.origin[0] - camera.x, self.origin[1] - camera.y
        cx, cy = ox + self.core[0], oy + self.core[1]
        c = config.COLORS
        if lit:
            pulse = 0.5 + 0.5 * math.sin(t * 2.2)
            self.halo.set_alpha(int(170 + 85 * pulse))
            surface.blit(self.halo, (cx - self.halo_r, cy - self.halo_r))
        surface.blit(self.stone, (ox, oy))
        if not lit:
            self.dim.set_alpha(int(150 + 40 * math.sin(t * 1.3)))
            surface.blit(self.dim, (ox, oy))
            return
        surface.blit(self.lit, (ox, oy))
        # 核から昇る光の粒（時間だけで決まる）
        for i in range(3):
            u = (t * 0.45 + i / 3) % 1.0
            px = cx + math.sin(u * 6.3 + i * 2.1) * 4
            py = cy - 4 - u * 34
            col = (*c["cp_core"], int(220 * (1 - u)))
            dot = pygame.Surface((2, 2), pygame.SRCALPHA); dot.fill(col)
            surface.blit(dot, (int(px), int(py)))
        # 起動の瞬間: 光の柱と、地面に広がる輪
        if age < self.FLASH_SECONDS:
            k = age / self.FLASH_SECONDS
            a = int(200 * (1 - k) ** 1.5)
            colw = int(10 + 18 * k)
            col_s = pygame.Surface((colw, int(self.floor_y - camera.y)), pygame.SRCALPHA)
            for i in range(colw):
                edge = 1 - abs(i - colw / 2) / (colw / 2)
                pygame.draw.line(col_s, (*c["cp_glow"], int(a * edge)), (i, 0), (i, col_s.get_height()))
            surface.blit(col_s, (cx - colw // 2, 0))
            rr = int(8 + 52 * k)
            ring = pygame.Surface((rr * 2 + 2, rr // 2 * 2 + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(ring, (*c["cp_core"], a), ring.get_rect(), 2)
            surface.blit(ring, (cx - rr - 1, self.floor_y - camera.y - ring.get_height() // 2))


class TerrainRenderer:
    """地形・一方通行足場・ゴールの描画。各地形は初期化時にサーフェス化する。"""

    def __init__(self, stage, seed: int = 3):
        rng = random.Random(seed)
        rects = [r.to_rect() for r in stage.platforms]
        self.pits = find_pits(rects, stage.world_width, stage.resolution[1])
        lefts = {x1 for _, x1, _ in self.pits}     # 穴の右端 = 右側の地面の左面
        rights = {x0 for x0, _, _ in self.pits}    # 穴の左端 = 左側の地面の右面
        view_h = stage.resolution[1]
        # v3.0: 縦スクロールのステージでは、城門・落とし穴を縦の範囲の下端まで描き、地中・地下の空洞も描く
        bounds = getattr(stage, "camera_bounds", None)
        self.vertical = bounds is not None
        self.view_h = view_h
        art_bottom = int(bounds[1]) if bounds else view_h
        # 通常の地面は従来どおり（乱数の消費順も変えない）。城門・地下は別の乱数で焼き込む
        under_rng = random.Random(seed + 101)
        self.solids = []
        for r, rect in zip(stage.platforms, rects):
            if r.style == "sealed_gate":
                continue
            if r.style == "underground":
                self.solids.append((rect, self._bake_underground(r, under_rng)))
            else:
                self.solids.append((rect, self._bake_ground(r, rng, rect.left in lefts, rect.right in rights)))
        self.gates = [SealedGateArt(rect, art_bottom, _gate_floor_y(rect, rects, view_h), seed=sum(map(ord, r.id)))
                      for r, rect in zip(stage.platforms, rects) if r.style == "sealed_gate"]
        self.one_ways = [(r.to_rect(), self._bake_one_way(r, rng)) for r in stage.one_way_platforms]
        self.pit_kinds = classify_pits(rects, self.pits, view_h)
        self.pit_images = []
        for (x0, x1, top), kind in zip(self.pits, self.pit_kinds):
            if kind == PIT_ENTRANCE:
                img = self._bake_shaft(x1 - x0, view_h - top)
            else:
                img = self._bake_pit(x1 - x0, art_bottom - top, glow_h=(view_h - top) if self.vertical else None)
            self.pit_images.append((x0, top, img))
        # 地下の空洞（地下の床の上、地上の床の下面まで）
        self.caves = []
        if self.vertical:
            for r in stage.platforms:
                if r.style == "underground" and r.y > view_h and r.w >= 200:   # 床だけ（階段・壁は除く）
                    cave = pygame.Rect(int(r.x), view_h, int(r.w), int(r.y - view_h))
                    self.caves.append((cave, self._bake_cave(cave.w, cave.h, under_rng)))
        self.goal_x = stage.goal_x
        self.time = 0.0
        # v2.5: チェックポイントの目印（描画のみ）。状態は World が set_checkpoint_lit で知らせる
        cp = getattr(stage, "checkpoint", None)
        self.checkpoint = None
        if cp is not None:
            floor = min((r.top for r in rects if r.left <= cp.x < r.right), default=cp.y + 40)
            self.checkpoint = CheckpointMarker(cp.x, floor, seed=sum(map(ord, cp.id)))
        self.checkpoint_lit = False
        self.checkpoint_age = 1e9      # 起動からの経過秒（起動の演出用）

    def set_checkpoint_lit(self, flash: bool = True) -> None:
        self.checkpoint_lit = True
        self.checkpoint_age = 0.0 if flash else 1e9

    @staticmethod
    def _bake_pit(w: int, h: int, glow_h: int | None = None) -> pygame.Surface:
        """v2.3: 穴の内部。上は黒く、底に向かって赤く光る（地面の暗灰色と色相で区別する）。描画のみ。

        v3.0: glow_h を指定すると、上端から glow_h の深さで赤が最も強くなり、それより下は赤のまま
        （縦スクロールのステージで落とし穴を下まで描いても、中層から見て赤く見えるように）。
        """
        surf = pygame.Surface((max(1, int(w)), max(1, int(h))))
        base = (5, 2, 5)
        glow = config.COLORS["pit_glow"]
        a_max = config.VISIBILITY["pit_glow_alpha"] / 255
        span = surf.get_height() if glow_h is None else max(1, int(glow_h))
        for y in range(surf.get_height()):
            k = min(1.0, y / max(1, span - 1))
            g = a_max * max(0.0, (k - 0.25) / 0.75) ** 1.6
            surf.fill(tuple(int(base[i] + (glow[i] - base[i]) * g) for i in range(3)), (0, y, w, 1))
        # 両側の壁面の影（奥行き）
        for i in range(6):
            shade = (0, 0, 0, int(150 * (1 - i / 6)))
            layer = pygame.Surface((1, surf.get_height()), pygame.SRCALPHA)
            layer.fill(shade)
            surf.blit(layer, (i, 0))
            surf.blit(layer, (surf.get_width() - 1 - i, 0))
        return surf

    @staticmethod
    def _bake_shaft(w: int, h: int) -> pygame.Surface:
        """v3.0: 地下への入口（竪穴）。底へ向かって青緑の水の光が強くなる（落とし穴の赤と区別する）。描画のみ。

        入口の下（ワールドの y > 画面の高さ）は地下の空洞として別に描くので、ここでは地上の床の下面まで。
        """
        w, h = max(1, int(w)), max(1, int(h))
        surf = pygame.Surface((w, h))
        base = config.COLORS["cave_back_far"]
        glow = config.COLORS["shaft_glow"]
        for y in range(h):
            k = y / max(1, h - 1)
            g = 0.75 * max(0.0, (k - 0.2) / 0.8) ** 1.4
            surf.fill(tuple(int(base[i] + (glow[i] - base[i]) * g) for i in range(3)), (0, y, w, 1))
        # 下へ続いていることを示す、壊れた格子と垂れる水の筋
        rng = random.Random(w * 31 + h)
        stone = config.COLORS["cave_stone_top"]
        for x in range(6, w - 4, 14):
            pygame.draw.line(surf, stone, (x, 0), (x + rng.randint(-3, 3), rng.randint(10, 26)), 2)
        for _ in range(max(2, w // 30)):
            x = rng.randint(4, max(5, w - 4))
            y0 = rng.randint(20, max(21, h // 2))
            pygame.draw.line(surf, (*config.COLORS["cave_water"],), (x, y0), (x, min(h - 1, y0 + rng.randint(20, 50))), 1)
        for i in range(6):   # 両側の壁面の影
            shade = (0, 0, 0, int(150 * (1 - i / 6)))
            layer = pygame.Surface((1, h), pygame.SRCALPHA)
            layer.fill(shade)
            surf.blit(layer, (i, 0))
            surf.blit(layer, (w - 1 - i, 0))
        return surf

    @staticmethod
    def _bake_cave(w: int, h: int, rng) -> pygame.Surface:
        """v3.0: 地下の空洞の奥の壁（地下水路・侵食された地下遺構）。描画のみ。"""
        c = config.COLORS
        surf = _vertical_gradient(w, h, [(0.0, c["cave_back_far"]), (1.0, c["cave_back"])])
        # 奥の石積み（古い地下遺構）
        for y in range(8, h - 8, 26):
            x = rng.randint(-20, 0)
            while x < w:
                bw = rng.randint(30, 60)
                v = rng.randint(-3, 5)
                col = tuple(max(0, min(255, k + v)) for k in c["cave_back"])
                pygame.draw.rect(surf, col, (x + 2, y + 2, bw - 4, 22), 1)
                x += bw
        # 侵食の青緑の脈（下から這い上がる）
        for _ in range(max(1, w // 160)):
            x, y = rng.randint(10, max(11, w - 10)), h - 1
            pts = [(x, y)]
            for _ in range(rng.randint(5, 9)):
                x += rng.randint(-14, 14)
                y -= rng.randint(10, 22)
                if y < 0:
                    break
                pts.append((x, y))
            if len(pts) > 1:
                pygame.draw.lines(surf, c["gate_vein_dark"], False, pts, 3)
                pygame.draw.lines(surf, c["cave_moss"], False, pts, 1)
        # 天井（地上の床の下面）からの水滴
        for _ in range(max(2, w // 60)):
            x = rng.randint(0, max(1, w - 1))
            pygame.draw.line(surf, c["cave_water"], (x, 0), (x, rng.randint(6, 18)), 1)
        return surf

    @staticmethod
    def _bake_underground(r, rng) -> pygame.Surface:
        """v3.0: 地下の床・壁・階段（湿った石、縁の苔、床の水の反射）。地面と同じく上に 24px の余白を持つ。"""
        c = config.COLORS
        w, h = int(r.w), int(r.h)
        surf = pygame.Surface((w, h + 24), pygame.SRCALPHA)
        top = 24
        pygame.draw.rect(surf, c["cave_stone"], (0, top, w, h))
        pygame.draw.rect(surf, c["cave_stone_top"], (0, top, w, 4))
        for _ in range(max(1, w // 36)):
            x = rng.randint(0, max(1, w - 16))
            y = rng.randint(top + 10, max(top + 11, top + h - 8))
            pygame.draw.rect(surf, (30, 32, 40), (x, y, rng.randint(8, 20), rng.randint(3, 7)))
        # 縁の苔（侵食の青緑）
        for x in range(0, w, 3):
            if rng.random() < 0.55:
                pygame.draw.line(surf, c["cave_moss"], (x, top + 1), (x, top - rng.randint(1, 5)), 1)
        # 床の水の反射（幅の広い床だけ）
        if w >= 120 and h < 200:
            for _ in range(w // 50):
                x = rng.randint(0, max(1, w - 30))
                pygame.draw.line(surf, c["cave_water"], (x, top + 6), (x + rng.randint(12, 30), top + 6), 1)
        pygame.draw.line(surf, (14, 14, 18), (0, top), (0, top + h), 2)
        pygame.draw.line(surf, (14, 14, 18), (w - 1, top), (w - 1, top + h), 2)
        return surf

    @staticmethod
    def _bake_ground(r, rng, left_edge: bool = False, right_edge: bool = False) -> pygame.Surface:
        w, h = int(r.w), int(r.h)
        surf = pygame.Surface((w, h + 24), pygame.SRCALPHA)
        top = 24
        pygame.draw.rect(surf, config.COLORS["ground"], (0, top, w, h))
        pygame.draw.rect(surf, config.COLORS["ground_top"], (0, top, w, 6))
        # 石と亀裂
        for _ in range(w // 40):
            x = rng.randint(0, max(1, w - 20))
            y = rng.randint(top + 14, top + h - 10)
            pygame.draw.rect(surf, (44, 34, 36), (x, y, rng.randint(8, 22), rng.randint(4, 9)))
        # 枯草
        for _ in range(w // 6):
            x = rng.uniform(0, w)
            length = rng.uniform(5, 18)
            lean = rng.uniform(-5, 5)
            col = config.COLORS["grass"] if rng.random() < 0.6 else (90, 74, 50)
            pygame.draw.line(surf, col, (x, top + 2), (x + lean, top - length), 1)
        # 側面の縁取り
        pygame.draw.line(surf, (20, 14, 16), (0, top), (0, top + h), 2)
        pygame.draw.line(surf, (20, 14, 16), (w - 1, top), (w - 1, top + h), 2)
        # v2.3: 穴に面した側面は明るい石の縁にする（上ほど明るく、下へ地面の色に溶ける）。描画のみ
        ew = config.VISIBILITY["ground_edge_width"]
        if ew > 0:
            edge, ground = config.COLORS["ground_edge"], config.COLORS["ground"]
            for side, on in ((0, left_edge), (1, right_edge)):
                if not on:
                    continue
                for y in range(h):
                    k = max(0.0, 1.0 - y / 70) if y > 6 else 1.0
                    col = tuple(int(ground[i] + (edge[i] - ground[i]) * k) for i in range(3))
                    x0 = 0 if side == 0 else w - ew
                    pygame.draw.line(surf, col, (x0, top + y), (x0 + ew - 1, top + y))
                # 角の欠けた石（縁の位置を上面でも示す）
                cx = 0 if side == 0 else w - 10
                pygame.draw.rect(surf, edge, (cx, top - 2, 10, 4))
        return surf

    @staticmethod
    def _bake_one_way(r, rng) -> pygame.Surface:
        w, h = int(r.w), int(r.h)
        surf = pygame.Surface((w, h + 60), pygame.SRCALPHA)
        # 崩れかけた石橋
        pygame.draw.rect(surf, config.COLORS["platform"], (0, 0, w, h))
        pygame.draw.rect(surf, config.COLORS["platform_top"], (0, 0, w, 3))
        for x in range(0, w, 32):
            pygame.draw.line(surf, (40, 32, 30), (x, 0), (x, h), 1)
        # 下に垂れる朽ちた布と鎖
        for _ in range(max(1, w // 64)):
            x = rng.randint(8, max(9, w - 16))
            ln = rng.randint(18, 50)
            pygame.draw.polygon(surf, (70, 20, 24),
                                [(x, h), (x + 10, h), (x + 7, h + ln), (x + 2, h + ln - 8)])
        return surf

    def update(self, dt: float) -> None:
        self.time += dt
        self.checkpoint_age += dt

    def draw(self, surface: pygame.Surface, camera) -> None:
        view = camera.view_rect.inflate(64, 64)
        if self.vertical:
            # 地上の床より下: 地中を塗り、地下の空洞を描く（その上に竪穴・落とし穴・地形を重ねる）
            ground_line = self.view_h - camera.y
            if ground_line < surface.get_height():
                top = max(0, int(ground_line))
                surface.fill(config.COLORS["earth"], (0, top, surface.get_width(), surface.get_height() - top))
                for cave, img in self.caves:
                    if view.colliderect(cave):
                        surface.blit(img, (cave.x - camera.x, cave.y - camera.y))
        for x0, top, img in self.pit_images:
            if view.colliderect(pygame.Rect(x0, top, img.get_width(), img.get_height())):
                surface.blit(img, (x0 - camera.x, top - camera.y))
        for rect, img in self.solids:
            if view.colliderect(rect):
                surface.blit(img, (rect.x - camera.x, rect.y - 24 - camera.y))
        cpm = self.checkpoint
        # 起動の演出（光の柱・輪）が目印より広がる分、判定を左右に 40px 広げる
        if cpm is not None and view.colliderect(pygame.Rect(cpm.origin[0] - 40, cpm.origin[1], cpm.W + 80, cpm.H)):
            cpm.draw(surface, camera, self.time, self.checkpoint_lit, self.checkpoint_age)
        for gate in self.gates:
            if view.colliderect(gate.rect):
                gate.draw(surface, camera, self.time)
        for rect, img in self.one_ways:
            if view.colliderect(rect.inflate(0, 120)):
                surface.blit(img, (rect.x - camera.x, rect.y - camera.y))
        # ゴール地点: 光る石碑
        gx = self.goal_x - camera.x
        if -60 < gx < surface.get_width() + 60:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3)
            glow = pygame.Surface((80, 300), pygame.SRCALPHA)
            for i in range(40):
                a = int((40 - i) * 2.2 * (0.6 + 0.4 * pulse))
                pygame.draw.line(glow, (255, 210, 140, a), (40 - i, 0), (40 - i, 300))
                pygame.draw.line(glow, (255, 210, 140, a), (40 + i, 0), (40 + i, 300))
            surface.blit(glow, (gx - 40 - 12, 122))
            pygame.draw.rect(surface, (30, 24, 28), (gx - 22, 330, 20, 92))
            pygame.draw.polygon(surface, (30, 24, 28), [(gx - 26, 330), (gx - 12, 312), (gx + 2, 330)])
            pygame.draw.rect(surface, (255, 200, 120), (gx - 15, 350, 6, 20))
