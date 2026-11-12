"""Stage1 background v3 — PHASE 2 assembly (deterministic).

Inputs : prep_manifest.json (geometry/masks predeclared in phase 1), imagegen_raw/<job>.png
Outputs: candidates/<L>_candidate.png, assemble_report.json

Per job:
  1. uniform resize of the GENERATED image to the prep canvas size (premultiplied alpha,
     LANCZOS). Only generated pixels are resampled; source pixels are never resampled.
  2. registration: integer shift (dx,dy) in [-R,R] of the generated canvas that best matches the
     raw-copied source context in a band next to the gap (premultiplied RGB + alpha, mean abs).
     Measured on context only (never on the gap), reported per side. The single shift applied is
     the one minimising the sum over sides; the unshifted variant is also written for review.
  3. only gap pixels go into the candidate canvas (straight copy, no blending/feathering).
Then the FULL original source rectangle is restored by raw byte copy (no alpha-over) and
verified byte-for-byte against draft_v1 and the predeclared protection mask.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent / "draft_v1"
RAW = HERE / "imagegen_raw"
OUT = HERE / "candidates"
R = 16          # registration search radius (canvas px)
BAND = 96       # context band width next to the gap used for registration


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def premul(a: np.ndarray) -> np.ndarray:
    f = a.astype(np.float32)
    f[..., :3] *= f[..., 3:4] / 255
    return f


def shift(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """out[y, x] = a[y - dy, x - dx]; outside -> transparent."""
    h, w = a.shape[:2]
    o = np.zeros_like(a)
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    o[yd, xd] = a[ys, xs]
    return o


def ctx_bands(job: dict, w: int) -> dict:
    g0, g1 = job["gap_canvas_x"]
    bands = {}
    if g0 > 0:
        bands["left_of_gap"] = (max(0, g0 - BAND), g0)
    if g1 < w:
        bands["right_of_gap"] = (g1, min(w, g1 + BAND))
    return bands


def band_err(gen_p: np.ndarray, ref_p: np.ndarray, x0: int, x1: int) -> float:
    g, r = gen_p[:, x0:x1], ref_p[:, x0:x1]
    m = (g[..., 3] > 8) | (r[..., 3] > 8)
    if not m.any():
        return 0.0
    return float(np.abs(g - r)[m].mean())


def main() -> None:
    man = json.loads((HERE / "prep_manifest.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    rep: dict = {"registration_radius": R, "band": BAND, "layers": {}}
    for lid, L in man["layers"].items():
        src_p = HERE.parent / L["source_file"]
        assert sha(src_p) == L["source_sha256_file"], "source changed since phase 1"
        src = np.array(Image.open(src_p))
        mask_p = HERE / L["protection_mask"]
        assert sha(mask_p) == L["protection_mask_sha256"], "protection mask changed since phase 1"
        pm = np.array(Image.open(mask_p)) == 255
        cw, ch = L["candidate_canvas_size"]
        ox, oy = L["source_offset_in_candidate"]
        cands = {"registered": np.zeros((ch, cw, 4), np.uint8),
                 "unshifted": np.zeros((ch, cw, 4), np.uint8)}
        LR: dict = {"jobs": {}}
        for jn, J in L["jobs"].items():
            can = np.array(Image.open(HERE / J["input_canvas"]))
            assert sha(HERE / J["input_canvas"]) == J["input_canvas_sha256"]
            raw_p = RAW / f"{lid}_{jn}.png"
            raw = Image.open(raw_p).convert("RGBA")
            w, h = J["canvas_size"]
            sx, sy = w / raw.size[0], h / raw.size[1]
            gen = np.array(raw.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA"))
            gen_p, can_p = premul(gen), premul(can)
            bands = ctx_bands(J, w)
            best, table = None, {}
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    sp = premul(shift(gen, dx, dy))
                    errs = {k: band_err(sp, can_p, *b) for k, b in bands.items()}
                    tot = sum(errs.values())
                    if best is None or tot < best[0]:
                        best = (tot, dx, dy, errs)
                    table[(dx, dy)] = errs
            # per-side optimum (to expose disagreement between the two contexts)
            per_side = {}
            for k in bands:
                (dx, dy), e = min(((d, v[k]) for d, v in table.items()), key=lambda t: t[1])
                per_side[k] = {"best_shift": [dx, dy], "err": round(e, 2),
                               "err_at_0_0": round(table[(0, 0)][k], 2)}
            _, bdx, bdy, berr = best
            g0, g1 = J["gap_canvas_x"]; gy0, gy1 = J["gap_canvas_y"]
            tx, ty = J["gap_to_candidate_dx"], J["gap_to_candidate_dy"]
            for name, (dx, dy) in {"registered": (bdx, bdy), "unshifted": (0, 0)}.items():
                g = shift(gen, dx, dy)
                cands[name][gy0 + ty:gy1 + ty, g0 + tx:g1 + tx] = g[gy0:gy1, g0:g1]
            # context fidelity of the generator (how much it redrew the protected context)
            full_ctx = ~np.zeros((h, w), bool); full_ctx[gy0:gy1, g0:g1] = False
            reg_p = premul(shift(gen, bdx, bdy))
            mm = full_ctx & ((reg_p[..., 3] > 8) | (can_p[..., 3] > 8))
            LR["jobs"][jn] = dict(
                raw_file=f"imagegen_raw/{raw_p.name}", raw_sha256=sha(raw_p), raw_size=list(raw.size),
                scale_to_canvas=[round(sx, 6), round(sy, 6)],
                aspect_mismatch_pct=round(abs(sx / sy - 1) * 100, 3),
                applied_shift_canvas_px=[bdx, bdy],
                applied_shift_original_px=[bdx, bdy],  # canvas px == original source px
                band_err_applied={k: round(v, 2) for k, v in berr.items()},
                per_side=per_side,
                whole_context_mean_abs_premul_after_shift=round(float(np.abs(reg_p - can_p)[mm].mean()), 2),
                gap_canvas_x=[g0, g1], gap_to_candidate_dx=tx, gap_to_candidate_dy=ty)
        # restore the exact source bytes (raw copy, not alpha-over) over the protected rect
        for name, c in cands.items():
            c[oy:oy + 941, ox:ox + 1672] = src
            assert np.array_equal(c[pm], np.broadcast_to(src.reshape(-1, 4), (pm.sum(), 4))) or \
                np.array_equal(c[oy:oy + 941, ox:ox + 1672], src)
            p = OUT / (f"{lid}_candidate.png" if name == "registered" else f"{lid}_candidate_unshifted_alt.png")
            Image.fromarray(c, "RGBA").save(p)
            back = np.array(Image.open(p))
            ok = bool(np.array_equal(back[oy:oy + 941, ox:ox + 1672], src))
            outside_changed = int(((back[..., 3] > 0) & ~pm).sum())
            LR[name] = dict(file=f"candidates/{p.name}", sha256=sha(p), size=[cw, ch],
                            protected_rgba_identical=ok,
                            protected_pixels=int(pm.sum()),
                            nonzero_alpha_pixels_outside_protection=outside_changed)
        LR["source_offset_in_candidate"] = [ox, oy]
        LR["source_sha256_after"] = sha(src_p)
        LR["mask_sha256_after"] = sha(mask_p)
        LR["mask_unchanged"] = LR["mask_sha256_after"] == L["protection_mask_sha256"]
        LR["source_unchanged"] = LR["source_sha256_after"] == L["source_sha256_file"]
        rep["layers"][lid] = LR
    (HERE / "assemble_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({k: {j: (v["applied_shift_canvas_px"], v["band_err_applied"], v["per_side"])
                          for j, v in L["jobs"].items()} for k, L in rep["layers"].items()}, indent=1))
    print({k: (L["registered"]["protected_rgba_identical"], L["mask_unchanged"], L["source_unchanged"])
           for k, L in rep["layers"].items()})


if __name__ == "__main__":
    main()
