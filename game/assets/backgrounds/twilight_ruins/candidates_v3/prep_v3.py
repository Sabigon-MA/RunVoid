"""Stage1 background v3 — PHASE 1 preparation (deterministic, no creative pixels).

What this script does (and nothing else):
  * hashes the draft_v1 source PNGs (read-only; never written);
  * declares, BEFORE any generation, the candidate canvas geometry, the source offset
    inside each candidate canvas, and the protection mask = the FULL original 1672x941
    source rectangle (every RGBA byte incl. alpha 0/1 holes);
  * builds outpainting input canvases for the coordinator's image_gen by RAW byte copy of
    unchanged source pixels next to a fully transparent (0,0,0,0) gap that is to be painted;
  * writes edit masks (white = may be generated, black = keep), protection masks, previews;
  * writes prep_manifest.json with all hashes/offsets.

It never feathers, clones, smears, mirrors, fills or resamples source pixels.
Run:  python prep_v3.py   (system Python with numpy + Pillow; paths are relative to this file)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent / "draft_v1"
PREP = HERE / "prep"
MASKS = HERE / "masks"
SW, SH = 1672, 941

# ---------------------------------------------------------------------------
# Predeclared geometry (fixed before generation; do not tune after seeing output)
# ---------------------------------------------------------------------------
# L1/L2: one bridge pad appended to the RIGHT of the source; source stays at (0,0), so the
#        original internal coordinate frame and 941 vertical registration are unchanged.
#        Tile period becomes SW + pad. The pad's right edge abuts the source's x=0 column of
#        the next tile, so the outpaint canvas = [right context | gap | left context].
# L3:    local outer pads left and right only (no bottom pad: bottom of the sprites sits
#        below the ground line and is hidden by terrain); source offset (L3_PAD_L, 0).
LAYERS = {
    "L1": dict(file="02_far_castle.png", kind="bridge", pad=320, ctx=546),
    "L2": dict(file="03_mid_invasion.png", kind="bridge", pad=384, ctx=514),
    "L3": dict(file="04_near_debris.png", kind="outer", pad_l=96, pad_r=128,
               y0=470, ctx_l=610, ctx_r=578),
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def arr_sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def save(a: np.ndarray, p: Path, mode: str) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a, mode).save(p, optimize=False)
    back = np.array(Image.open(p))
    assert back.shape == a.shape and np.array_equal(back, a), p  # lossless round trip
    return sha(p)


def checker_preview(rgba: np.ndarray, gap: np.ndarray) -> np.ndarray:
    """Viewing aid only: source alpha-composited on dark plum; gap shown as magenta hatch."""
    h, w = rgba.shape[:2]
    bg = np.empty((h, w, 3), np.float32); bg[:] = (26, 16, 30)
    a = rgba[..., 3:4].astype(np.float32) / 255
    out = rgba[..., :3].astype(np.float32) * a + bg * (1 - a)
    yy, xx = np.mgrid[0:h, 0:w]
    hatch = ((xx + yy) // 12) % 2 == 0
    out[gap & hatch] = (255, 0, 255); out[gap & ~hatch] = (90, 0, 90)
    return out.clip(0, 255).astype(np.uint8)


def main() -> None:
    man: dict = {"source_dir": "draft_v1", "source_size": [SW, SH], "layers": {},
                 "protection_policy": (
                     "Protection mask = the full original 1672x941 source rectangle at its offset in "
                     "the candidate canvas; every RGBA byte inside it (including alpha 0/1 transparent "
                     "holes and semitransparent edges) must equal draft_v1 exactly. Not an alpha "
                     "threshold and not a semantic building mask. Declared before any generation.")}
    for lid, cfg in LAYERS.items():
        src_p = SRC_DIR / cfg["file"]
        im = Image.open(src_p); assert im.mode == "RGBA" and im.size == (SW, SH)
        src = np.array(im)
        L: dict = {"source_file": f"draft_v1/{cfg['file']}", "source_sha256_file": sha(src_p),
                   "source_sha256_rgba_bytes": arr_sha(src)}
        if cfg["kind"] == "bridge":
            pad, ctx = cfg["pad"], cfg["ctx"]
            cw, ch = SW + pad, SH
            off = (0, 0)
            # outpaint canvas: right context (source x SW-ctx..SW-1) | gap | left context (x 0..ctx-1)
            can = np.zeros((SH, ctx + pad + ctx, 4), np.uint8)
            can[:, :ctx] = src[:, SW - ctx:]
            can[:, ctx + pad:] = src[:, :ctx]
            gap = np.zeros(can.shape[:2], bool); gap[:, ctx:ctx + pad] = True
            jobs = {"bridge": dict(canvas=can, gap=gap,
                                   map={"gap_canvas_x": [ctx, ctx + pad], "gap_canvas_y": [0, SH],
                                        "gap_to_candidate_dx": SW - ctx, "gap_to_candidate_dy": 0,
                                        "left_context_source_x": [SW - ctx, SW],
                                        "right_context_source_x": [0, ctx]})}
            L["tile_period_px_original_scale"] = cw
        else:
            pl, pr, y0 = cfg["pad_l"], cfg["pad_r"], cfg["y0"]
            cw, ch = pl + SW + pr, SH
            off = (pl, 0)
            hh = SH - y0
            canl = np.zeros((hh, pl + cfg["ctx_l"], 4), np.uint8)
            canl[:, pl:] = src[y0:, :cfg["ctx_l"]]
            gapl = np.zeros(canl.shape[:2], bool); gapl[:, :pl] = True
            canr = np.zeros((hh, cfg["ctx_r"] + pr, 4), np.uint8)
            canr[:, :cfg["ctx_r"]] = src[y0:, SW - cfg["ctx_r"]:]
            gapr = np.zeros(canr.shape[:2], bool); gapr[:, cfg["ctx_r"]:] = True
            jobs = {
                "outer_left": dict(canvas=canl, gap=gapl,
                                   map={"gap_canvas_x": [0, pl], "gap_canvas_y": [0, hh],
                                        "gap_to_candidate_dx": 0, "gap_to_candidate_dy": y0,
                                        "context_source_x": [0, cfg["ctx_l"]], "context_source_y": [y0, SH]}),
                "outer_right": dict(canvas=canr, gap=gapr,
                                    map={"gap_canvas_x": [cfg["ctx_r"], cfg["ctx_r"] + pr], "gap_canvas_y": [0, hh],
                                         "gap_to_candidate_dx": pl + SW - cfg["ctx_r"], "gap_to_candidate_dy": y0,
                                         "context_source_x": [SW - cfg["ctx_r"], SW], "context_source_y": [y0, SH]}),
            }
            L["note_rows_above_y0"] = (f"candidate pad rows 0..{y0 - 1} stay fully transparent: no source "
                                       f"content touches the outer edges above y={y0} (edge content starts at y>=720)")
        # protection mask in candidate-canvas coordinates
        pm = np.zeros((ch, cw), np.uint8); pm[off[1]:off[1] + SH, off[0]:off[0] + SW] = 255
        L.update(candidate_canvas_size=[cw, ch], source_offset_in_candidate=list(off),
                 protection_mask=f"masks/{lid}_protect_full_source_rect.png",
                 protection_mask_sha256=save(pm, MASKS / f"{lid}_protect_full_source_rect.png", "L"),
                 protection_mask_kind="FULL original source rectangle (strongest; not semantic)",
                 protected_pixel_count=int((pm == 255).sum()), jobs={})
        for jn, j in jobs.items():
            base = f"{lid}_{jn}"
            can, gap = j["canvas"], j["gap"]
            em = np.where(gap, 255, 0).astype(np.uint8)
            # the copied context must be byte-identical to source (raw copy check)
            L["jobs"][jn] = dict(
                input_canvas=f"prep/{base}_canvas_rgba.png",
                input_canvas_sha256=save(can, PREP / f"{base}_canvas_rgba.png", "RGBA"),
                edit_mask=f"prep/{base}_editmask_white_is_generate.png",
                edit_mask_sha256=save(em, PREP / f"{base}_editmask_white_is_generate.png", "L"),
                edit_mask_alpha_style=f"prep/{base}_editmask_openai_alpha0_is_generate.png",
                preview=f"prep/{base}_preview_gap_magenta.png",
                canvas_size=[can.shape[1], can.shape[0]], **j["map"])
            ea = np.full(can.shape[:2] + (4,), 255, np.uint8); ea[gap, 3] = 0; ea[gap, :3] = 0
            L["jobs"][jn]["edit_mask_alpha_style_sha256"] = save(
                ea, PREP / f"{base}_editmask_openai_alpha0_is_generate.png", "RGBA")
            save(checker_preview(can, gap), PREP / f"{base}_preview_gap_magenta.png", "RGB")
        man["layers"][lid] = L
    (HERE / "prep_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: (v["candidate_canvas_size"], v["source_offset_in_candidate"]) for k, v in man["layers"].items()}))


if __name__ == "__main__":
    main()
