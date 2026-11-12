"""Static QA images for v4 (writes only candidates_v4/qa_v4). Measurement/visualisation only."""
import json
import numpy as np
from PIL import Image, ImageDraw

D = 'game/assets/backgrounds/twilight_ruins/'
V3 = D + 'candidates_v3/candidates/'
V4 = D + 'candidates_v4/'
O = V4 + 'qa_v4/'
PM = json.load(open(V4 + 'prep_manifest_v4.json'))
SRC = {L: D + PM['protection'][L]['source_file'] for L in ('L1', 'L2', 'L3')}
V3F = {'L1': V3 + 'L1_candidate.png', 'L2': V3 + 'L2_candidate.png', 'L3': V3 + 'L3_candidate.png'}
V4F = {'L1': V4 + 'candidates/L1_v4_candidate.png', 'L2': V4 + 'candidates/L2_v4_candidate.png',
       'L3': V4 + 'candidates/L3_v4_candidate.png'}
BGS = {'dark': (28, 18, 32), 'black': (0, 0, 0), 'white': (255, 255, 255), 'cyan': (0, 200, 220),
       'L0sky': None}
SKY = np.array(Image.open(D + 'draft_v1/01_sky.png').convert('RGB'))


def load(p):
    return np.array(Image.open(p).convert('RGBA'))


def comp(a, bg):
    f = a.astype(float); al = f[..., 3:4] / 255
    if bg is None:  # L0 sky stretched to same height, tiled horizontally
        sky = np.array(Image.fromarray(SKY).resize((SKY.shape[1] * a.shape[0] // SKY.shape[0], a.shape[0])))
        reps = -(-a.shape[1] // sky.shape[1])
        b = np.tile(sky, (1, reps, 1))[:, :a.shape[1]].astype(float)
    else:
        b = np.array(bg, float)
    return (f[..., :3] * al + b * (1 - al)).astype(np.uint8)


def game_scale(a):
    w = round(a.shape[1] * 960 / 1672)
    f = a.astype(np.float64); p = np.concatenate([f[..., :3] * f[..., 3:4] / 255, f[..., 3:4]], -1)
    ch = [np.array(Image.fromarray(p[..., i].astype(np.float32), 'F').resize((w, 540), Image.LANCZOS)) for i in range(4)]
    p = np.clip(np.stack(ch, -1), 0, 255); al = p[..., 3:4]
    rgb = np.where(al > 0, p[..., :3] * 255 / np.maximum(al, 1e-6), 0)
    return np.concatenate([np.clip(rgb, 0, 255), al], -1).round().astype(np.uint8)


def label(img, text):
    im = Image.fromarray(img) if isinstance(img, np.ndarray) else img
    d = ImageDraw.Draw(im); d.rectangle([0, 0, 8 + 6 * len(text), 13], fill=(0, 0, 0)); d.text((3, 1), text, fill=(255, 255, 255))
    return im


def hstack(ims, gap=6, bg=(90, 90, 90)):
    h = max(i.height for i in ims); w = sum(i.width for i in ims) + gap * (len(ims) - 1)
    out = Image.new('RGB', (w, h), bg); x = 0
    for i in ims:
        out.paste(i, (x, 0)); x += i.width + gap
    return out


def vstack(ims, gap=6, bg=(90, 90, 90)):
    w = max(i.width for i in ims); h = sum(i.height for i in ims) + gap * (len(ims) - 1)
    out = Image.new('RGB', (w, h), bg); y = 0
    for i in ims:
        out.paste(i, (0, y)); y += i.height + gap
    return out


def crop_join(a, x, y0, y1, half, zoom, bg=(28, 18, 32), wrap_src=None):
    """crop centred on boundary x (pixels left of x | right of x). wrap_src: for outer seams, right side from source x0."""
    if wrap_src is not None:
        left = a[y0:y1, a.shape[1] - half:]
        right = wrap_src[y0:y1, :half]
        c = np.concatenate([left, right], 1)
    else:
        c = a[y0:y1, max(0, x - half):x + half]
    im = Image.fromarray(comp(c, bg)).resize((c.shape[1] * zoom, c.shape[0] * zoom), Image.NEAREST)
    d = ImageDraw.Draw(im)
    bx = (half if wrap_src is not None else x - max(0, x - half)) * zoom
    d.line([(bx, 0), (bx, 6)], fill=(0, 255, 0), width=2); d.line([(bx, im.height - 7), (bx, im.height)], fill=(0, 255, 0), width=2)
    return im


JOINS = {  # (name, boundary x in candidate coords, rows, kind)
    'L1': [('inner_x1672', 1672, (360, 680), 'inner'), ('outer_wrap', None, (540, 680), 'outer')],
    'L2': [('inner_x1672', 1672, (440, 700), 'inner'), ('outer_wrap_upper', None, (140, 460), 'outer'),
           ('outer_wrap_lower', None, (440, 700), 'outer')],
    'L3': [('left_inner_x96', 96, (700, 941), 'inner'), ('right_inner_x1768_HELDv3', 1768, (700, 941), 'inner')],
}

summary = {}
for L in ('L1', 'L2', 'L3'):
    src, v3, v4 = load(SRC[L]), load(V3F[L]), load(V4F[L])
    ox = PM['protection'][L]['source_offset'][0]
    H, W = v4.shape[:2]
    # ---- edit scope ----
    es = comp(v4, (28, 18, 32)).copy()
    added = np.ones((H, W), bool); added[:, ox:ox + 1672] = False
    es[added & (v4[..., 3] > 0)] = (es[added & (v4[..., 3] > 0)] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
    im = Image.fromarray(es); d = ImageDraw.Draw(im)
    d.rectangle([ox, 0, ox + 1671, 940], outline=(0, 255, 0), width=3)
    for jn, j in PM['jobs'].items():
        if j['layer'] != L:
            continue
        c0 = j['candidate_gap_x'][0]
        pts = [(c0 + x, y) for x, y in j['guides_source_coords']['forbid_above']]
        d.line(pts, fill=(255, 40, 40), width=3)
        r0, r1 = j['source_rows']; c1 = j['candidate_gap_x'][1]
        d.rectangle([c0, r0, c1, r1], outline=(255, 220, 0), width=2)
    if L == 'L3':
        d.rectangle([1768, 0, 1895, 940], outline=(0, 160, 255), width=3)
    label(im, f'{L} v4 edit scope: green=protected source rect, magenta=new pixels, yellow=generation band, red=forbid line, blue=v3 HELD pad').save(O + f'{L}_v4_edit_scope.png')
    # ---- source-coordinate diff ----
    reg = v4[:, ox:ox + 1672]
    ch = np.any(reg != src, -1)
    dimg = np.zeros((941, W, 3), np.uint8)
    dimg[:, ox:ox + 1672][~ch] = (0, 70, 0); dimg[:, ox:ox + 1672][ch] = (255, 0, 0)
    dimg[added] = np.stack([v4[..., 3][added]] * 3, -1) * np.array([1, 0, 1])
    label(dimg, f'{L} source-coord diff: dark green=equal ({int((~ch).sum())}), red=changed ({int(ch.sum())}), magenta=new alpha').save(O + f'{L}_v4_diff_source_coords.png')
    # ---- original / v3 / v4 join comparisons ----
    for name, x, (y0, y1), kind in JOINS[L]:
        for zoom, half in ((1, 160), (4, 40)):
            rows = []
            for tag, a in (('original', None), ('v3', v3), ('v4', v4)):
                if tag == 'original':
                    if kind == 'outer':
                        # original period wrap: source right edge | source x0
                        c = np.concatenate([src[y0:y1, 1672 - half:], src[y0:y1, :half]], 1)
                    else:
                        pad = np.zeros((941, 1672 + 2 * ox if L == 'L3' else W, 4), np.uint8)
                        pad[:, ox:ox + 1672] = src
                        c = pad[y0:y1, max(0, x - half):x + half]
                    im = Image.fromarray(comp(c, (28, 18, 32))).resize((c.shape[1] * zoom, c.shape[0] * zoom), Image.NEAREST)
                else:
                    im = crop_join(a, x, y0, y1, half, zoom, wrap_src=src if kind == 'outer' else None)
                rows.append(label(im, f'{tag}'))
            hstack(rows).save(O + f'{L}_join_{name}_{zoom}x_orig_v3_v4.png')
    # ---- tiles at game scale ----
    if L in ('L1', 'L2'):
        g = game_scale(v4)
        for n in (2, 3):
            t = np.tile(g, (1, n, 1))
            for bgn in ('dark', 'cyan'):
                im = Image.fromarray(comp(t, BGS[bgn])); d = ImageDraw.Draw(im)
                for k in range(n):
                    d.line([(k * g.shape[1] + 960, 0), (k * g.shape[1] + 960, 8)], fill=(0, 255, 0), width=2)
                    if k:
                        d.line([(k * g.shape[1], 0), (k * g.shape[1], 8)], fill=(255, 255, 0), width=2)
                label(im, f'{L} v4 x{n} game scale period {g.shape[1]}px (green=inner join, yellow=outer seam) REJECTED').save(O + f'{L}_v4_{n}tile_{bgn}.png')
    else:
        g = game_scale(v4)
        for bgn in ('dark', 'cyan'):
            label(Image.fromarray(comp(g, BGS[bgn])), 'L3 v4 game scale (L3 is decoration atlas, not tiled)').save(O + f'L3_v4_gamescale_{bgn}.png')
    # ---- alpha checks over black/white/bg/L0 sky (game scale) ----
    g = game_scale(v4)
    hstack([label(Image.fromarray(comp(g, BGS[b])), b) for b in ('black', 'white', 'dark', 'L0sky')]).save(O + f'{L}_v4_alpha_check_bg4.png')
    # halo metric: low-alpha (1..32) pixels among NEW pixels
    na = v4[..., 3][added]; sa = src[..., 3]
    summary[L] = {'new_pixels_alpha_gt0': int((na > 0).sum()), 'new_low_alpha_1_32_frac': round(float(((na > 0) & (na <= 32)).sum() / max(1, (na > 0).sum())), 3),
                  'source_low_alpha_1_32_frac': round(float(((sa > 0) & (sa <= 32)).sum() / max(1, (sa > 0).sum())), 3),
                  'changed_protected_pixels': int(ch.sum())}
json.dump(summary, open(O + 'qa_v4_summary.json', 'w'), indent=1)
print(json.dumps(summary))
