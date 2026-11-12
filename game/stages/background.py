"""画像素材による多層パララックス背景（ステージJSONの "background" で設定）。

レイヤー構成（ステージ1「黄昏の廃王国」の例）:
    L0 空        factor 0.00  画面固定（不透明）
    L1 遠景の廃城 factor 0.15  横方向に繰り返し
    L2 中景の侵食都市 factor 0.40  横方向に繰り返し
    L3 近景の瓦礫・枯草 factor 0.75  ステージ座標に個別配置するデコレーション

方針:
    * 画像の読み込み・拡大縮小・継ぎ目処理はすべて初期化時に1回だけ行う。
      毎フレームは blit のみ（画面に掛かるタイルとデコレーションだけ）。
    * 素材パスはこのファイルの位置（game/）基準で解決し、カレントディレクトリに依存しない。
    * 画像が無い・壊れている場合は BackgroundAssetError を送出する。
      呼び出し側（renderer.make_background）がそれだけを捕捉して手続き背景へ戻す。
      設定の誤りやプログラムの誤りは握りつぶさない。
    * 背景は地形・キャラクターより先に描くだけで、当たり判定には一切関与しない。

繰り返しレイヤーの継ぎ目処理（seam）:
    "none"      元画像をそのまま周期 = 画像幅で並べる（隙間は出ないが端の切れ目は見える）
    "feather"   左右端 width px のアルファを滑らかに 0 へ落とす（端の硬い切れ目を霞に溶かす）
    "crossfade" 右端 width px と左端 width px を線形に重ねて周期 = 幅 - width にする
                （構図は維持されるが重ねた帯では2つの建物が半透明に二重に見える）
    どの方式も原画の構図・中央部は変更しない。処理は画像の両端の帯だけに限られる。
"""
from __future__ import annotations

import bisect
import logging
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

import pygame

GAME_DIR = Path(__file__).resolve().parent.parent

log = logging.getLogger("runvoid.background")

SEAM_MODES = ("none", "feather", "crossfade")


class BackgroundConfigError(ValueError):
    """背景設定（JSON）の誤り。フォールバックせずに送出する。"""


class BackgroundAssetError(RuntimeError):
    """背景画像の欠落・破損。手続き背景へのフォールバック対象。"""


# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class SeamDef:
    mode: str = "none"
    width: int = 0          # 960x540 に縮小した後の画素数


@dataclass(frozen=True)
class LayerDef:
    id: str
    image: str
    factor: float
    repeat: bool
    seam: SeamDef = SeamDef()


@dataclass(frozen=True)
class SpriteDef:
    id: str
    src: tuple[int, int, int, int]       # 元画像の画素座標 (x, y, w, h)
    fade_left: int = 0                   # 元画像の端で切れている辺をぼかす幅（縮小後の画素）
    fade_right: int = 0
    # Previous crop retained as the placement/resampling reference when src grows.
    anchor_src: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class PlacementDef:
    sprite: str
    x: float          # ステージX座標。画面中央に来たとき地形と同じ位置に見える（スプライト中心）
    bottom: float     # ステージY座標（スプライト下端）


@dataclass(frozen=True)
class DecorationLayerDef:
    id: str
    image: str
    factor: float
    sprites: tuple[SpriteDef, ...]
    placements: tuple[PlacementDef, ...]
    period: float | None = None   # 指定時は配置をこの間隔で繰り返す（タイトル画面の無限スクロール用）


@dataclass(frozen=True)
class ShadeDef:
    """地面の高さより下を暗く落とす帯（穴を足場と見誤らないため。旧背景の奈落表現と同じ目的）。"""
    top: int
    height: int
    color: tuple[int, int, int]
    max_alpha: int


@dataclass(frozen=True)
class GroundConnectorDef:
    before_layer: str
    shade: ShadeDef


@dataclass(frozen=True)
class BackgroundConfig:
    asset_dir: str
    layers: tuple[LayerDef, ...]
    decorations: DecorationLayerDef | None = None
    ground_shade: ShadeDef | None = None
    ground_connector: GroundConnectorDef | None = None

    @property
    def asset_path(self) -> Path:
        return GAME_DIR / self.asset_dir


def _num(raw, key, where, default=None, lo=None, hi=None) -> float:
    if key not in raw:
        if default is None:
            raise BackgroundConfigError(f"{where}: '{key}' がありません")
        return default
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BackgroundConfigError(f"{where}.{key}: 有限の数値にしてください")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise BackgroundConfigError(f"{where}.{key}: {lo}〜{hi} の範囲にしてください")
    return float(value)


def _str(raw, key, where) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise BackgroundConfigError(f"{where}: '{key}' は空でない文字列にしてください")
    return value


def _dict(raw, where) -> dict:
    if not isinstance(raw, dict):
        raise BackgroundConfigError(f"{where}: オブジェクトにしてください")
    return raw


def _parse_seam(raw, where) -> SeamDef:
    if raw is None:
        return SeamDef()
    raw = _dict(raw, where)
    mode = raw.get("mode", "none")
    if mode not in SEAM_MODES:
        raise BackgroundConfigError(f"{where}.mode: {SEAM_MODES} のいずれかにしてください")
    width = int(_num(raw, "width", where, default=0, lo=0, hi=400))
    if mode != "none" and width <= 0:
        raise BackgroundConfigError(f"{where}.width: '{mode}' には正の幅が必要です")
    return SeamDef(mode, width)


def _parse_layer(raw, where) -> LayerDef:
    raw = _dict(raw, where)
    factor = _num(raw, "factor", where, lo=0.0, hi=1.0)
    repeat = raw.get("repeat", factor > 0)
    if not isinstance(repeat, bool):
        raise BackgroundConfigError(f"{where}.repeat: true/false にしてください")
    if not repeat and factor != 0:
        # 繰り返さないレイヤーが動くと画面外へ流れて空白ができる
        raise BackgroundConfigError(f"{where}: repeat=false のレイヤーは factor 0 にしてください")
    seam = _parse_seam(raw.get("seam"), f"{where}.seam")
    if seam.mode != "none" and not repeat:
        raise BackgroundConfigError(f"{where}.seam: 繰り返さないレイヤーには指定できません")
    return LayerDef(_str(raw, "id", where), _str(raw, "image", where), factor, repeat, seam)


def _parse_decorations(raw, where) -> DecorationLayerDef:
    raw = _dict(raw, where)
    factor = _num(raw, "factor", where, lo=0.0, hi=1.0)
    if factor <= 0:
        raise BackgroundConfigError(f"{where}.factor: デコレーションは 0 より大きくしてください")
    sprites = []
    for sid, sraw in _dict(raw.get("sprites", {}), f"{where}.sprites").items():
        sw = f"{where}.sprites.{sid}"
        sraw = _dict(sraw, sw)
        src = sraw.get("src")
        if (not isinstance(src, list) or len(src) != 4
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in src)):
            raise BackgroundConfigError(f"{sw}.src: [x, y, w, h] の整数4つにしてください")
        if src[0] < 0 or src[1] < 0 or src[2] <= 0 or src[3] <= 0:
            raise BackgroundConfigError(f"{sw}.src: 位置は0以上、幅と高さは正にしてください")
        anchor = sraw.get("anchor_src")
        if anchor is not None:
            if (not isinstance(anchor, list) or len(anchor) != 4
                    or not all(isinstance(v, int) and not isinstance(v, bool) for v in anchor)
                    or anchor[2] <= 0 or anchor[3] <= 0
                    or not pygame.Rect(src).contains(pygame.Rect(anchor))):
                raise BackgroundConfigError(f"{sw}.anchor_src: src 内の正の矩形を指定してください")
        sprites.append(SpriteDef(str(sid), tuple(src),
                                 int(_num(sraw, "fade_left", sw, default=0, lo=0, hi=200)),
                                 int(_num(sraw, "fade_right", sw, default=0, lo=0, hi=200)),
                                 tuple(anchor) if anchor is not None else None))
    if not sprites:
        raise BackgroundConfigError(f"{where}.sprites: 1つ以上必要です")
    ids = {s.id for s in sprites}
    period = raw.get("period")
    if period is not None:
        period = _num(raw, "period", where, lo=1.0)
    placements = []
    items = raw.get("placements", [])
    if not isinstance(items, list):
        raise BackgroundConfigError(f"{where}.placements: 配列にしてください")
    for i, praw in enumerate(items):
        pw = f"{where}.placements[{i}]"
        praw = _dict(praw, pw)
        sprite = _str(praw, "sprite", pw)
        if sprite not in ids:
            raise BackgroundConfigError(f"{pw}.sprite: 未定義のスプライト '{sprite}'")
        x = _num(praw, "x", pw)
        if period is not None and not 0 <= x < period:
            raise BackgroundConfigError(f"{pw}.x: period 指定時は 0 以上 period 未満にしてください")
        placements.append(PlacementDef(sprite, x, _num(praw, "bottom", pw)))
    return DecorationLayerDef(_str(raw, "id", where), _str(raw, "image", where), factor,
                              tuple(sprites), tuple(placements), period)


def _parse_shade(raw, where) -> ShadeDef | None:
    if raw is None:
        return None
    raw = _dict(raw, where)
    color = raw.get("color", [4, 2, 4])
    if (not isinstance(color, list) or len(color) != 3
            or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in color)):
        raise BackgroundConfigError(f"{where}.color: 0〜255 の整数3つにしてください")
    return ShadeDef(int(_num(raw, "top", where, lo=0)), int(_num(raw, "height", where, default=40, lo=1)),
                    tuple(color), int(_num(raw, "max_alpha", where, default=255, lo=0, hi=255)))


def parse_background(raw) -> BackgroundConfig | None:
    """ステージJSONの "background" を検証する。省略・"procedural" なら None（従来の手続き背景）。"""
    if raw is None:
        return None
    raw = _dict(raw, "background")
    kind = raw.get("type", "parallax_images")
    if kind == "procedural":
        return None
    if kind != "parallax_images":
        raise BackgroundConfigError("background.type: 'parallax_images' か 'procedural' にしてください")
    asset_dir = _str(raw, "asset_dir", "background")
    win, posix = PureWindowsPath(asset_dir), PurePosixPath(asset_dir)
    # Windows では "/x" も "C:x" も is_absolute() が False なので anchor で判定する
    if win.anchor or posix.is_absolute() or ".." in win.parts:
        raise BackgroundConfigError("background.asset_dir: game/ からの相対パスにしてください")
    layers_raw = raw.get("layers")
    if not isinstance(layers_raw, list) or not layers_raw:
        raise BackgroundConfigError("background.layers: 1つ以上のレイヤー配列が必要です")
    layers = tuple(_parse_layer(l, f"background.layers[{i}]") for i, l in enumerate(layers_raw))
    if layers[0].factor != 0 or layers[0].repeat:
        raise BackgroundConfigError("background.layers[0]: 最背面は factor 0 の固定レイヤーにしてください")
    deco = raw.get("decorations")
    decorations = _parse_decorations(deco, "background.decorations") if deco is not None else None
    ids = [l.id for l in layers] + ([decorations.id] if decorations else [])
    if len(set(ids)) != len(ids):
        raise BackgroundConfigError("background: レイヤー id が重複しています")
    connector = None
    if raw.get("ground_connector") is not None:
        cr = _dict(raw["ground_connector"], "background.ground_connector")
        before = _str(cr, "before_layer", "background.ground_connector")
        if before not in [l.id for l in layers[1:]]:
            raise BackgroundConfigError("background.ground_connector.before_layer: 空以外の画像レイヤーを指定してください")
        connector = GroundConnectorDef(before, _parse_shade(cr, "background.ground_connector"))
    return BackgroundConfig(asset_dir, layers, decorations,
                            _parse_shade(raw.get("ground_shade"), "background.ground_shade"), connector)


# ----------------------------------------------------------------------
# 初期化時の画像処理
# ----------------------------------------------------------------------
def load_image(path: Path) -> pygame.Surface:
    """画像を読み込む。欠落・破損だけを BackgroundAssetError に変換する。"""
    try:
        surface = pygame.image.load(str(path))
    except (FileNotFoundError, pygame.error, OSError) as exc:
        raise BackgroundAssetError(f"背景画像を読み込めません: {path} ({exc})") from exc
    if surface.get_bitsize() != 32 or not surface.get_flags() & pygame.SRCALPHA:
        # 24bit PNG なども 32bit アルファ形式に揃える（ウィンドウ無しでも動く方法で）
        rgba = pygame.Surface(surface.get_size(), pygame.SRCALPHA, 32)
        rgba.blit(surface, (0, 0))
        surface = rgba
    return surface


def _display_ready() -> bool:
    return pygame.display.get_init() and pygame.display.get_surface() is not None


def _optimize(surface: pygame.Surface, alpha: bool) -> pygame.Surface:
    """画面のピクセル形式へ変換（ウィンドウが無いテスト環境ではそのまま）。"""
    if not _display_ready():
        return surface
    return surface.convert_alpha() if alpha else surface.convert()


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _ramp_mask(w: int, h: int, left: int, right: int, channels_all: bool) -> pygame.Surface:
    """左右端で 0→1 に上がる乗算マスク。channels_all=False ならアルファのみ乗算。"""
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    mask.fill((255, 255, 255, 255))
    for i in range(w):
        k = 1.0
        if left > 0 and i < left:
            k = min(k, _smoothstep((i + 0.5) / left))
        if right > 0 and i >= w - right:
            k = min(k, _smoothstep((w - i - 0.5) / right))
        if k < 1.0:
            v = int(round(255 * k))
            col = (v, v, v, v) if channels_all else (255, 255, 255, v)
            pygame.draw.line(mask, col, (i, 0), (i, h - 1))
    return mask


def fade_edges(surface: pygame.Surface, left: int, right: int, premultiplied: bool = False) -> pygame.Surface:
    """左右端のアルファを滑らかに 0 へ落とした複製を返す。"""
    out = surface.copy()
    if left > 0 or right > 0:
        mask = _ramp_mask(out.get_width(), out.get_height(), left, right, premultiplied)
        out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def make_seamless(surface: pygame.Surface, seam: SeamDef) -> pygame.Surface:
    """繰り返しタイル（乗算済みアルファ形式）を作る。戻り値の幅が繰り返し周期。

    surface は通常のアルファ形式。描画時は BLEND_PREMULTIPLIED で合成する
    （crossfade の線形合成を正しく行うため、全方式で乗算済み形式に統一）。
    """
    w, h = surface.get_size()
    premul = surface.premul_alpha()
    if seam.mode == "none" or seam.width <= 0:
        return premul
    k = seam.width
    if seam.mode == "feather":
        if 2 * k > w:
            raise BackgroundConfigError("seam.width が画像幅の半分を超えています")
        return fade_edges(premul, k, k, premultiplied=True)
    # crossfade: 周期 P = w - k。先頭 k 列 = 右端 k 列(1-t) + 左端 k 列(t)
    if 2 * k >= w:
        raise BackgroundConfigError("seam.width が画像幅の半分を超えています")
    period = w - k
    out = pygame.Surface((period, h), pygame.SRCALPHA)
    # 空の out への加算 = 画素値そのままのコピー（通常の blit はアルファ合成になるため使わない）
    out.blit(premul, (k, 0), area=pygame.Rect(k, 0, w - 2 * k, h), special_flags=pygame.BLEND_RGBA_ADD)
    left = premul.subsurface((0, 0, k, h)).copy()
    right = premul.subsurface((w - k, 0, k, h)).copy()
    fade_in = pygame.Surface((k, h), pygame.SRCALPHA)
    fade_out = pygame.Surface((k, h), pygame.SRCALPHA)
    for i in range(k):
        t = (i + 0.5) / k
        a, b = int(round(255 * t)), int(round(255 * (1 - t)))
        pygame.draw.line(fade_in, (a, a, a, a), (i, 0), (i, h - 1))
        pygame.draw.line(fade_out, (b, b, b, b), (i, 0), (i, h - 1))
    left.blit(fade_in, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    right.blit(fade_out, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    right.blit(left, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    out.blit(right, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return out


def _alpha_crop(surface: pygame.Surface) -> tuple[pygame.Surface, int]:
    """完全透明な上下の行を切り詰める（毎フレームの合成画素数を減らす）。"""
    bounds = surface.get_bounding_rect(min_alpha=1)
    if bounds.height == 0:
        return pygame.Surface((surface.get_width(), 1), pygame.SRCALPHA), 0
    rect = pygame.Rect(0, bounds.y, surface.get_width(), bounds.height)
    return surface.subsurface(rect).copy(), bounds.y


# ----------------------------------------------------------------------
# 描画
# ----------------------------------------------------------------------
class ImageLayer:
    """1枚絵のパララックスレイヤー。repeat=True なら周期 period で横に並べる。"""

    def __init__(self, layer_id: str, surface: pygame.Surface, factor: float, y: int,
                 repeat: bool, premultiplied: bool):
        self.id = layer_id
        self.surface = surface
        self.factor = factor
        self.y = y
        self.repeat = repeat
        self.period = surface.get_width()
        self.flags = pygame.BLEND_PREMULTIPLIED if premultiplied else 0

    def tile_positions(self, camera_x: float, view_w: int) -> list[int]:
        """画面に掛かるタイルの左端X（整数）。負・小数のカメラ位置にも対応する。"""
        if not self.repeat:
            return [0]
        p = self.period
        shift = (camera_x * self.factor) % p
        if shift >= p:          # 浮動小数の丸めで p ちょうどになる場合
            shift -= p
        x = -int(shift)         # shift >= 0 なので切り捨て = floor
        out = []
        while x < view_w:
            out.append(x)
            x += p
        return out

    def draw(self, target: pygame.Surface, camera_x: float) -> None:
        for x in self.tile_positions(camera_x, target.get_width()):
            target.blit(self.surface, (x, self.y), special_flags=self.flags)


class DecorationLayer:
    """ステージ座標に個別配置する近景デコレーション（画面内のものだけ描く）。"""

    def __init__(self, layer_id: str, sprites: dict[str, pygame.Surface], placements, factor: float,
                 view_w: int, period: float | None, origins: dict[str, tuple[float, float]] | None = None):
        self.id = layer_id
        self.sprites = sprites
        self.factor = factor
        self.view_w = view_w
        self.period = period
        self.origins = {key: (-img.get_width()/2, -img.get_height()) for key, img in sprites.items()}
        if origins:
            self.origins.update(origins)
        self.items = sorted(placements, key=lambda p: p.x)
        self.xs = [p.x for p in self.items]
        self.max_half_w = max((max(abs(self.origins[key][0]),
                                  abs(self.origins[key][0]+img.get_width()))
                               for key, img in sprites.items()), default=0) + 1

    def screen_pos(self, placement: PlacementDef, camera_x: float, offset: float = 0.0) -> tuple[int, int]:
        c = self.view_w / 2
        cx = c + (placement.x + offset - camera_x - c) * self.factor
        ox, oy = self.origins[placement.sprite]
        return int(math.floor(cx + ox)), int(round(placement.bottom + oy))

    def visible(self, camera_x: float) -> list[tuple[str, int, int]]:
        """画面に掛かる配置だけを (sprite, x, y) で返す。"""
        if not self.items:
            return []
        c = self.view_w / 2
        # 画面中心からの距離 d のスプライト中心は c + d*factor に描かれる
        lo = camera_x + c - (c + self.max_half_w) / self.factor
        hi = camera_x + c + (self.view_w - c + self.max_half_w) / self.factor
        offsets = [0.0]
        if self.period:
            p = self.period
            offsets = [k * p for k in range(math.floor(lo / p) - 1, math.floor(hi / p) + 1)]
        out = []
        for off in offsets:
            i0 = bisect.bisect_left(self.xs, lo - off)
            i1 = bisect.bisect_right(self.xs, hi - off)
            for item in self.items[i0:i1]:
                x, y = self.screen_pos(item, camera_x, off)
                w = self.sprites[item.sprite].get_width()
                if x + w > 0 and x < self.view_w:
                    out.append((item.sprite, x, y))
        return out

    def draw(self, target: pygame.Surface, camera_x: float) -> None:
        for sprite, x, y in self.visible(camera_x):
            target.blit(self.sprites[sprite], (x, y))


class ParallaxImageBackground:
    """画像レイヤー + 近景デコレーション + 地面下の陰。update/draw は手続き背景と同じ形。"""

    def __init__(self, config: BackgroundConfig, view_w: int, view_h: int):
        self.config = config
        self.view_w, self.view_h = view_w, view_h
        base = config.asset_path
        self.layers: list[ImageLayer] = []
        for index, ld in enumerate(config.layers):
            src = load_image(base / ld.image)
            scaled = pygame.transform.smoothscale(src, (view_w, view_h))
            if ld.repeat:
                tile = make_seamless(scaled, ld.seam)
                tile, y = _alpha_crop(tile)
                # convert_alpha は画素値を変えないので乗算済みのまま画面形式にできる
                self.layers.append(ImageLayer(ld.id, _optimize(tile, alpha=True), ld.factor, y, True, True))
            else:
                # 最背面（空）は画面全体を覆う不透明レイヤーとして高速に blit する
                self.layers.append(ImageLayer(ld.id, _optimize(scaled, alpha=index > 0),
                                              ld.factor, 0, False, False))
        self.decorations = None
        if config.decorations:
            self.decorations = self._build_decorations(config.decorations, base)
        self.shade = self._build_shade(config.ground_shade) if config.ground_shade else None
        self.shade_y = config.ground_shade.top if config.ground_shade else 0
        self.connector = self._build_shade(config.ground_connector.shade) if config.ground_connector else None

    def _build_decorations(self, dd: DecorationLayerDef, base: Path) -> DecorationLayer:
        src = load_image(base / dd.image)
        sw, sh = src.get_size()
        kx, ky = self.view_w / sw, self.view_h / sh   # 背景全体と同じ縮尺
        sprites, origins = {}, {}
        for sd in dd.sprites:
            rect = pygame.Rect(sd.src)
            if not src.get_rect().contains(rect):
                raise BackgroundConfigError(f"{dd.id}.sprites.{sd.id}: src が画像 {sw}x{sh} の外です")
            if sd.anchor_src is None:
                size = (max(1, round(rect.w * kx)), max(1, round(rect.h * ky)))
                img = pygame.transform.smoothscale(src.subsurface(rect), size)
                img = fade_edges(img, sd.fade_left, sd.fade_right)
            else:
                anchor = pygame.Rect(sd.anchor_src)
                if not rect.contains(anchor):
                    raise BackgroundConfigError(f"{dd.id}.{sd.id}: anchor_src が src の外です")
                reference_size = (max(1, round(anchor.w*kx)), max(1, round(anchor.h*ky)))
                left, top = round((anchor.left-rect.left)*kx), round((anchor.top-rect.top)*ky)
                right, bottom = round((rect.right-anchor.right)*kx), round((rect.bottom-anchor.bottom)*ky)
                size = (left+reference_size[0]+right, top+reference_size[1]+bottom)
                img = pygame.transform.smoothscale(src.subsurface(rect), size)
                img = fade_edges(img, sd.fade_left, sd.fade_right)
                # Restore the reference crop using its original sampling grid and alpha.
                # Copy bytes rather than alpha-over: original translucent pixels stay identical.
                reference = pygame.transform.smoothscale(src.subsurface(anchor), reference_size)
                reference = fade_edges(reference, sd.fade_left if left == 0 else 0,
                                       sd.fade_right if right == 0 else 0)
                img.fill((0, 0, 0, 0), (left, top, *reference_size))
                img.blit(reference, (left, top), special_flags=pygame.BLEND_RGBA_ADD)
                origins[sd.id] = (-reference_size[0]/2-left, -reference_size[1]-top)
            sprites[sd.id] = _optimize(img, alpha=True)
        return DecorationLayer(dd.id, sprites, dd.placements, dd.factor, self.view_w, dd.period, origins)

    def _build_shade(self, sd: ShadeDef) -> pygame.Surface:
        h = max(1, self.view_h - sd.top)
        surf = pygame.Surface((self.view_w, h), pygame.SRCALPHA)
        for y in range(h):
            a = int(sd.max_alpha * min(1.0, (y + 1) / sd.height))
            pygame.draw.line(surf, (*sd.color, a), (0, y), (self.view_w - 1, y))
        return _optimize(surf, alpha=True)

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface, camera_x: float) -> None:
        for layer in self.layers:
            if self.connector is not None and layer.id == self.config.ground_connector.before_layer:
                surface.blit(self.connector, (0, self.config.ground_connector.shade.top))
            layer.draw(surface, camera_x)
        if self.decorations:
            self.decorations.draw(surface, camera_x)
        if self.shade is not None:
            surface.blit(self.shade, (0, self.shade_y))


_CACHE: dict = {}


def build_background(config: BackgroundConfig, view_w: int, view_h: int) -> ParallaxImageBackground:
    """背景を構築する。同じ設定・解像度ならリトライ時に再読み込みせず使い回す（状態を持たないため安全）。"""
    key = (config, view_w, view_h, _display_ready())
    bg = _CACHE.get(key)
    if bg is None:
        bg = ParallaxImageBackground(config, view_w, view_h)
        _CACHE[key] = bg
    return bg


def clear_cache() -> None:
    _CACHE.clear()
