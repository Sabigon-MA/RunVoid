"""Stage1 background v4 — PHASE 2 assembly + predeclared gates (deterministic).

Generated pixels: uniform resize of the raw output to the local canvas (premultiplied, LANCZOS),
optional integer shift (+-3, only if both join sides agree within 2px), then ONLY gap pixels inside the
declared row band are placed. Protected source is restored by RAW byte copy from draft_v1 (no alpha-over),
then the PNG is saved, reloaded and compared. L3 right pad = raw copy of v3 candidate pixels (HELD, provenance).
No blur/feather/clone/average anywhere.
"""
import hashlib, json
import numpy as np
from PIL import Image, ImageDraw

D = 'game/assets/backgrounds/twilight_ruins/'
V3 = D + 'candidates_v3/'
V4 = D + 'candidates_v4/'
PM = json.load(open(V4 + 'prep_manifest_v4.json'))


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def load(p):
    return np.array(Image.open(p).convert('RGBA'))


def premul(a):
    f = a.astype(np.float64)
    return np.concatenate([f[..., :3] * f[..., 3:4] / 255.0, f[..., 3:4]], -1)


def resize_premul(a, size):
    f = premul(a)
    ch = [np.array(Image.fromarray(f[..., i].astype(np.float32), 'F').resize(size, Image.LANCZOS)) for i in range(4)]
    p = np.clip(np.stack(ch, -1), 0, 255)
    al = p[..., 3:4]
    rgb = np.where(al > 0, p[..., :3] * 255.0 / np.maximum(al, 1e-6), 0)
    return np.concatenate([np.clip(rgb, 0, 255), al], -1).round().astype(np.uint8)


def shift(a, dx, dy):
    out = np.zeros_like(a)
    H, W = a.shape[:2]
    ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
    xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
    out[yd, xd] = a[ys, xs]
    return out


def side_err(gen, ctx, x0, x1):
    g, c = premul(gen[:, x0:x1]), premul(ctx[:, x0:x1])
    m = (g[..., 3] > 0) | (c[..., 3] > 0)
    return float(np.abs(g - c)[m].mean()) if m.any() else 0.0


def register(gen, ctx, gx0, gx1, ring=16, R=3):
    sides = {}
    W = ctx.shape[1]
    if gx0 > 0:
        sides['left_of_gap'] = (gx0 - ring, gx0)
    if gx1 < W:
        sides['right_of_gap'] = (gx1, gx1 + ring)
    res = {}
    for s, (a, b) in sides.items():
        best = None
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                e = side_err(shift(gen, dx, dy), ctx, a, b)
                if best is None or e < best[0]:
                    best = (e, dx, dy)
        res[s] = {'best_shift': [best[1], best[2]], 'err': round(best[0], 2),
                  'err_at_0_0': round(side_err(gen, ctx, a, b), 2)}
    bs = [v['best_shift'] for v in res.values()]
    agree = all(abs(p[0] - q[0]) <= 2 and abs(p[1] - q[1]) <= 2 for p in bs for q in bs)
    if agree and len(bs) == 2:
        applied = [int(round((bs[0][0] + bs[1][0]) / 2)), int(round((bs[0][1] + bs[1][1]) / 2))]
    elif len(bs) == 1:
        applied = bs[0]
    else:
        applied = [0, 0]
    return res, agree, applied


def extents(col):
    a = col.reshape(-1, 4)[:, 3]
    out = {}
    for t in (8, 128):
        nz = np.nonzero(a >= t)[0]
        out[f'a{t}'] = [int(nz.min()), int(nz.max())] if len(nz) else None
    return out


def contour_gate(ca, cb):
    ea, eb = extents(ca), extents(cb)
    d = {}
    ok = True
    for t in ('a8', 'a128'):
        if ea[t] is None and eb[t] is None:
            d[t] = 'both empty'
            continue
        if (ea[t] is None) != (eb[t] is None):
            d[t] = f'one side empty: src={ea[t]} pad={eb[t]}'
            ok = False
            continue
        dt, db = abs(ea[t][0] - eb[t][0]), abs(ea[t][1] - eb[t][1])
        d[t] = {'src': ea[t], 'pad': eb[t], 'top_delta': dt, 'bottom_delta': db}
        ok &= dt <= 4 and db <= 4
    return ok, d


def value_gate(src_strip, pad_strip, base_a, base_b):
    def mae(a, b):
        pa, pb = premul(a), premul(b)
        m = (pa[..., 3] > 0) | (pb[..., 3] > 0)
        return float(np.abs(pa[..., :3] - pb[..., :3])[m].mean()) if m.any() else 0.0
    j, b = mae(src_strip, pad_strip), mae(base_a, base_b)
    r = j / max(b, 1e-6)
    return r <= 2.5, {'join_mae': round(j, 2), 'source_baseline_mae': round(b, 2), 'ratio': round(r, 2)}


def forbid_mask(H, W, poly_gap, cand_gx0, gap_flip=False):
    im = Image.new('L', (W, H), 0)
    pts = [(cand_gx0 + x, y) for x, y in poly_gap]
    poly = [(pts[0][0], 0)] + pts + [(pts[-1][0], 0)]
    ImageDraw.Draw(im).polygon(poly, fill=255)
    return np.array(im) > 0


def assemble(L, jobname, out_name):
    prot = PM['protection'][L]
    W, H = prot['canvas_size']; ox = prot['source_offset'][0]
    src = load(D + prot['source_file'])
    assert sha(D + prot['source_file']) == prot['source_sha256']
    cand = np.zeros((H, W, 4), np.uint8)
    rep = {}
    jobs = [jobname] if isinstance(jobname, str) else jobname
    for jn in jobs:
        j = PM['jobs'][jn]
        ctx = load(V4 + j['canvas_local']['file'])
        raw_p = V4 + f'imagegen_raw/{jn}.png'
        raw = load(raw_p)
        lw, lh = j['local_canvas_size']
        sx, sy = lw / raw.shape[1], lh / raw.shape[0]
        gen = resize_premul(raw, (lw, lh))
        gx0, gx1 = j['gap_local_x'][0], j['gap_local_x'][1] + 1
        regs, agree, applied = register(gen, ctx, gx0, gx1)
        g2 = agree
        if agree:
            gen = shift(gen, applied[0], applied[1])
        else:
            applied = [0, 0]
        r0, r1 = j['source_rows'][0], j['source_rows'][1] + 1
        c0, c1 = j['candidate_gap_x'][0], j['candidate_gap_x'][1] + 1
        cand[r0:r1, c0:c1] = gen[:, gx0:gx1]
        rep[jn] = {'raw_file': f'imagegen_raw/{jn}.png', 'raw_sha256': sha(raw_p), 'raw_size': [raw.shape[1], raw.shape[0]],
                   'scale_raw_to_local': [round(sx, 6), round(sy, 6)],
                   'aspect_mismatch_pct': round(abs(sx / sy - 1) * 100, 3),
                   'registration': regs, 'G2_sides_agree': g2, 'applied_shift_local_px': applied,
                   'placed_rows': [r0, r1 - 1], 'placed_cols': [c0, c1 - 1],
                   'rows_outside_band_in_gap': 'alpha 0 (declared, not generated)'}
    if L == 'L3':
        v3 = load(V3 + 'candidates/L3_candidate.png')
        cand[:, 1768:1896] = v3[:, 1768:1896]
        rep['L3_right_held'] = {'provenance': 'raw copy candidates_v3/candidates/L3_candidate.png x1768..1895 all rows',
                                'v3_sha256': sha(V3 + 'candidates/L3_candidate.png')}
    cand[0:941, ox:ox + 1672] = src  # RAW byte copy, no alpha-over
    p = V4 + 'candidates/' + out_name
    Image.fromarray(cand, 'RGBA').save(p)
    re = load(p)
    region = re[0:941, ox:ox + 1672]
    changed = int(np.any(region != src, axis=-1).sum())
    rep['protection_equality_proof'] = {
        'method': 'PNG save -> reload -> np.array_equal(candidate[0:941, ox:ox+1672], draft_v1 RGBA) + per-pixel count',
        'identical': bool(np.array_equal(region, src)), 'protected_pixels': 1672 * 941, 'changed_protected_pixels': changed,
        'source_sha256_after': sha(D + prot['source_file'])}
    rep['candidate_file'] = 'candidates/' + out_name
    rep['candidate_sha256'] = sha(p)
    rep['canvas_size'] = [W, H]; rep['source_offset'] = [ox, 0]; rep['source_size'] = [1672, 941]
    return re, src, rep


def gates_for(L, cand, src, rep):
    W = cand.shape[1]
    g = {}
    if L in ('L1', 'L2'):
        # inner: source col 1671 | pad col 1672 ; outer (wrap): pad col W-1 | source col 0
        pairs = {'inner_x1672': (cand[:, 1670:1672], cand[:, 1672:1674], cand[:, 1668:1670], cand[:, 1671:1672], cand[:, 1672:1673]),
                 'outer_wrap': (src[:, 0:2], cand[:, W - 2:W], src[:, 2:4], src[:, 0:1], cand[:, W - 1:W])}
    else:
        pairs = {'left_inner_x96': (cand[:, 96:98], cand[:, 94:96], cand[:, 98:100], cand[:, 96:97], cand[:, 95:96]),
                 'right_inner_x1768_HELD_v3': (cand[:, 1766:1768], cand[:, 1768:1770], cand[:, 1764:1766], cand[:, 1767:1768], cand[:, 1768:1769])}
    for n, (s2, p2, b2, sc, pc) in pairs.items():
        okc, dc = contour_gate(sc, pc)
        okv, dv = value_gate(s2, p2, s2, b2)
        g[n] = {'G3_contour': {'pass': bool(okc), **dc}, 'G4_value': {'pass': bool(okv), **dv}}
    # G5 forbidden zones
    f = {}
    for jn in [k for k in rep if k in PM['jobs']]:
        j = PM['jobs'][jn]
        gd = j['guides_source_coords']
        c0, c1 = j['candidate_gap_x'][0], j['candidate_gap_x'][1] + 1
        m = forbid_mask(cand.shape[0], W, gd['forbid_above'], c0)
        m[:, :c0] = False; m[:, c1:] = False
        a = cand[..., 3]
        bad = m & (a > 8)
        f[jn] = {'forbid_pixels': int(m.sum()), 'violations_alpha_gt8': int(bad.sum()),
                 'max_alpha_in_forbid': int(a[m].max()) if m.any() else 0, 'pass': bool(bad.sum() == 0)}
    g['G5_forbidden_zone'] = f
    return g


if __name__ == '__main__':
    out = {}
    for L, jn, fn in (('L1', 'L1_fog', 'L1_v4_candidate.png'), ('L2', 'L2_lowrib', 'L2_v4_candidate.png'),
                      ('L3', 'L3L_rock', 'L3_v4_candidate.png')):
        cand, src, rep = assemble(L, jn, fn)
        rep['gates'] = gates_for(L, cand, src, rep)
        out[L] = rep
    json.dump(out, open(V4 + 'assemble_report_v4.json', 'w'), indent=1)
    for L, r in out.items():
        print(L, 'changed_protected', r['protection_equality_proof']['changed_protected_pixels'])
        for k, v in r['gates'].items():
            print('  ', k, json.dumps(v)[:400])
        for jn in PM['jobs']:
            if jn in r:
                print('   reg', jn, r[jn]['registration'], r[jn]['G2_sides_agree'], r[jn]['applied_shift_local_px'], r[jn]['aspect_mismatch_pct'])
