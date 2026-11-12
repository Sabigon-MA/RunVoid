"""Stage1 background v4 — PHASE 1 (deterministic, pre-generation declaration).

Writes ONLY under candidates_v4/. Reads draft_v1 (official, read-only) and candidates_v3 (read-only).
No artwork is invented here: outputs are crops of exact source pixels, transparent gaps,
binary masks, and explicit reference guides (lines/hatching) that are NEVER composited into a candidate.

Final candidate geometry is IDENTICAL to v3 (same canvas size / source offset / pad widths), so
v3 masks are reused as the exact protection reference (hash-checked here).

Local jobs (tighter than v3: small context, cropped rows, upscaled to an image_gen native size):
  L1_fog     : ctx src x1544..1671 | gap 320 | ctx src x0..127, rows 300..683  -> 576x384 (x2.6667 -> 1536x1024)
  L2_lowrib  : ctx src x1544..1671 | gap 384 | ctx src x0..127, rows 100..739  -> 640x640 (x1.6    -> 1024x1024)
  L3L_rock   : gap 96 | ctx src x0..263, rows 701..940                          -> 360x240 (x4.2667 -> 1536x1024)
L3 right pad is NOT regenerated: v3 pixels retained with provenance (HELD).
"""
import hashlib, json, os
import numpy as np
from PIL import Image, ImageDraw

D = 'game/assets/backgrounds/twilight_ruins/'
V3 = D + 'candidates_v3/'
V4 = D + 'candidates_v4/'
SRC = {'L1': D + 'draft_v1/02_far_castle.png', 'L2': D + 'draft_v1/03_mid_invasion.png',
       'L3': D + 'draft_v1/04_near_debris.png'}
CANVAS = {'L1': (1992, 941, 0), 'L2': (2056, 941, 0), 'L3': (1896, 941, 96)}  # w,h,source_offset_x (same as v3)


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def save(img, rel):
    p = V4 + rel
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p, optimize=False)
    return {'file': rel, 'sha256': sha(p), 'size': list(img.size)}


def up(img, size, nearest=False):
    return img.resize(size, Image.NEAREST if nearest else Image.LANCZOS)


JOBS = {
    'L1_fog': dict(layer='L1', rows=(300, 684), left_ctx=(1544, 1672), gap=320, right_ctx=(0, 128),
                   out=(1536, 1024), cand_gap_x=(1672, 1992)),
    'L2_lowrib': dict(layer='L2', rows=(100, 740), left_ctx=(1544, 1672), gap=384, right_ctx=(0, 128),
                      out=(1024, 1024), cand_gap_x=(1672, 2056)),
    'L3L_rock': dict(layer='L3', rows=(701, 941), left_ctx=None, gap=96, right_ctx=(0, 264),
                     out=(1536, 1024), cand_gap_x=(0, 96)),
}

# ---- explicit guides, in LOCAL canvas coords (x relative to canvas, y = source row - rows[0]) ----
# All guide coordinates come from measurements in prep/source_edge_alpha_runs.json,
# prep/source_edge_profiles_alpha_luma_step4.json and the rock/grass column scan (see README).
GUIDES = {
    # L1: wall ends inside source (x>=1665 alpha<8 above row 355; x1671 opaque a>=128 rows 408..623).
    # Seam (src x0): thin fog only, a>=8 rows 600..642, max alpha 39.
    'L1_fog': dict(
        top_contour=[(0, 408), (60, 430), (140, 480), (220, 545), (300, 590), (320, 598)],  # gap-x, src row
        bottom_line=[(0, 646), (320, 642)],
        forbid_above=[(0, 400), (320, 590)],  # anything above this polyline must stay alpha 0
        notes='hill/haze mass descends and thins to translucent fog (alpha<=~40) at gap-x>=260; no ruins/stubs'),
    # L2: source right edge terrain a>=128 rows 526..635 (a>=8 517..636). Seam (src x0): rib/lattice/ruin
    # column opaque rows 175..639 (a>=8 174..645). Stub zone = last 72 gap px only.
    'L2_lowrib': dict(
        top_contour=[(0, 517), (120, 515), (220, 505), (300, 470), (312, 440)],
        bottom_line=[(0, 636), (384, 640)],
        stub_zone=(312, 384),
        stub_top=[(312, 150), (384, 174)],
        forbid_above=[(0, 500), (240, 495), (312, 430), (312, 140), (384, 160)],
        notes='low rubble/terrain only in gap-x<312; gap-x 312..383: interrupted rib/lattice stubs continuing '
              'the cut x0 ribs leftward in tangent, broken off (no closing, no peak, no new arch)'),
    # L3 left: rock face at src x0..12 rows ~864..918 (sat scan), grass above to a>=8 row ~732.
    'L3L_rock': dict(
        rock_top=[(96, 864), (60, 862), (30, 868), (10, 880)],  # gap x (0..95), src row; rock closes by gap-x~8
        rock_bottom=[(96, 918), (10, 918)],
        forbid_above=[(0, 840), (60, 760), (96, 732)],
        notes='continue the SAME boulder (same top height/face/lit edge) and close its left end; grass tips; '
              'no separate low rock, no new tree'),
}


def build_job(name, j):
    src = np.array(Image.open(SRC[j['layer']]).convert('RGBA'))
    r0, r1 = j['rows']
    parts, gx0 = [], 0
    if j['left_ctx']:
        parts.append(src[r0:r1, j['left_ctx'][0]:j['left_ctx'][1]])
        gx0 = j['left_ctx'][1] - j['left_ctx'][0]
    gap = np.zeros((r1 - r0, j['gap'], 4), np.uint8)
    parts.append(gap)
    parts.append(src[r0:r1, j['right_ctx'][0]:j['right_ctx'][1]])
    canvas = np.concatenate(parts, axis=1)
    H, W = canvas.shape[:2]
    gx1 = gx0 + j['gap']
    assert abs(W / H - j['out'][0] / j['out'][1]) < 1e-9, (name, W, H)
    k = j['out'][0] / W
    m = np.zeros((H, W), np.uint8); m[:, gx0:gx1] = 255
    rec = {'layer': j['layer'], 'source_rows': [r0, r1 - 1], 'local_canvas_size': [W, H],
           'gap_local_x': [gx0, gx1 - 1], 'candidate_gap_x': [j['cand_gap_x'][0], j['cand_gap_x'][1] - 1],
           'left_ctx_source_x': [j['left_ctx'][0], j['left_ctx'][1] - 1] if j['left_ctx'] else None,
           'right_ctx_source_x': [j['right_ctx'][0], j['right_ctx'][1] - 1],
           'upscale_for_generator': k, 'generator_input_size': list(j['out']),
           'upscale_note': 'LANCZOS upscale of the INPUT only (generator readability). Output is downscaled back '
                           'to the local canvas; only gap pixels are used; protected source is raw-copied from draft_v1.'}
    ci = Image.fromarray(canvas)
    rec['canvas_local'] = save(ci, f'prep/{name}_canvas_local_rgba.png')
    rec['canvas_gen_input'] = save(up(ci, j['out']), f'prep/{name}_GENINPUT_canvas_{j["out"][0]}x{j["out"][1]}.png')
    mi = Image.fromarray(m)
    rec['mask_local_white_generate'] = save(mi, f'masks/{name}_generate_mask_local_white_is_generate.png')
    rec['mask_gen_white_generate'] = save(up(mi, j['out'], True),
                                          f'prep/{name}_GENINPUT_mask_white_is_generate.png')
    oa = np.zeros((H, W, 4), np.uint8); oa[..., 3] = 255 - m
    rec['mask_gen_openai_alpha0_generate'] = save(up(Image.fromarray(oa), j['out'], True),
                                                  f'prep/{name}_GENINPUT_mask_alpha0_is_generate.png')
    # ---- guide image (reference only) ----
    g = GUIDES[name]
    al = canvas[..., 3:4].astype(float) / 255
    comp = (canvas[..., :3] * al + np.array([28, 18, 32.]) * (1 - al)).astype(np.uint8)
    comp[:, gx0:gx1] = (60, 60, 64)
    gi = Image.fromarray(comp).convert('RGB')
    gi = up(gi, j['out'], True)
    dr = ImageDraw.Draw(gi)

    def P(pts):
        return [((gx0 + x) * k, (y - r0) * k) for x, y in pts]
    # red hatch = must remain transparent (alpha 0)
    fa = P(g['forbid_above'])
    poly = [(gx0 * k, 0)] + fa + [(gx1 * k, 0)]
    hatch = Image.new('L', gi.size, 0); ImageDraw.Draw(hatch).polygon(poly, fill=255)
    hm = np.array(hatch) > 0
    yy, xx = np.mgrid[0:gi.size[1], 0:gi.size[0]]
    stripe = ((xx + yy) // 10) % 3 == 0
    ga = np.array(gi); ga[hm & stripe] = (200, 30, 30); gi = Image.fromarray(ga); dr = ImageDraw.Draw(gi)
    for key, col in (('top_contour', (40, 230, 60)), ('rock_top', (40, 230, 60)), ('bottom_line', (40, 120, 255)),
                     ('rock_bottom', (40, 120, 255)), ('stub_top', (255, 220, 0))):
        if key in g:
            dr.line(P(g[key]), fill=col, width=4)
    if 'stub_zone' in g:
        for x in g['stub_zone']:
            dr.line([((gx0 + x) * k, 0), ((gx0 + x) * k, gi.size[1])], fill=(255, 220, 0), width=3)
    dr.rectangle([gx0 * k, 0, gx1 * k - 1, gi.size[1] - 1], outline=(255, 0, 255), width=3)
    rec['guide_reference_only'] = save(gi, f'prep/{name}_GENINPUT_guide_reference_only.png')
    rec['guides_source_coords'] = g
    return rec


def protection():
    out = {}
    for L, (w, h, ox) in CANVAS.items():
        m = np.zeros((h, w), np.uint8); m[0:941, ox:ox + 1672] = 255
        r = save(Image.fromarray(m), f'masks/{L}_protect_full_source_rect_v4.png')
        v3m = np.array(Image.open(V3 + f'masks/{L}_protect_full_source_rect.png').convert('L'))
        r['identical_to_v3_mask_pixels'] = bool(np.array_equal(v3m > 0, m > 0))
        r['v3_mask_sha256'] = sha(V3 + f'masks/{L}_protect_full_source_rect.png')
        r['canvas_size'] = [w, h]; r['source_offset'] = [ox, 0]; r['source_size'] = [1672, 941]
        r['source_file'] = SRC[L].replace(D, ''); r['source_sha256'] = sha(SRC[L])
        r['kind'] = 'FULL original 1672x941 source rectangle incl. fully transparent pixels/openings (raw-copy restore)'
        out[L] = r
    return out


GATES = {
    'G1_protected_exact': 'candidate[0:941, ox:ox+1672] == draft_v1 RGBA bytes after PNG save+reload; 0 changed pixels (HARD)',
    'G2_registration': 'integer shift search limited to +-3 canvas px (v3 used +-16) on a 16px context ring at each join; '
                       'if per-side best shifts disagree by >2px the attempt is REJECTED (no compromise shift)',
    'G3_join_contour': 'per join: |top of alpha>=128 run| and |bottom of alpha>=8| between source edge column and adjacent '
                       'pad column <= 4 original px (for the mass touching the join)',
    'G4_join_value': 'per join: mean |premultiplied RGB| between source edge 2-col strip and pad 2-col strip over rows with '
                     'alpha>0, divided by the source natural baseline (diff between its own cols e and e-/+2) <= 2.5',
    'G5_forbidden_zone': 'all new pixels in the red-hatched forbid region have alpha <= 8 (no new architecture/landmark)',
    'G6_visual': '1x and original-pixel zoom inspection over dark/black/white/bg-colour; any visible cut/step/halo = FAIL',
    'policy': 'Any gate FAIL -> join FAIL. No blur/feather/clone/average to hide a failure. Failed attempts are kept and labelled.',
}

if __name__ == '__main__':
    man = {'schema': 'runvoid.bg.candidates_v4.prep/1', 'adopted': False,
           'final_candidate_geometry': 'identical to v3 (canvas, source_offset, pad widths)',
           'protection': protection(), 'jobs': {n: build_job(n, j) for n, j in JOBS.items()},
           'acceptance_gates_predeclared': GATES,
           'L3_right': {'status': 'HELD partial candidate (not regenerated, not adopted)',
                        'provenance': 'candidates_v3/candidates/L3_candidate.png x1768..1895 rows 0..940, raw copy',
                        'v3_candidate_sha256': sha(V3 + 'candidates/L3_candidate.png')}}
    json.dump(man, open(V4 + 'prep_manifest_v4.json', 'w'), indent=1)
    print(json.dumps({L: v['identical_to_v3_mask_pixels'] for L, v in man['protection'].items()}))
