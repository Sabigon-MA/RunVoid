"""Stage1 background v3 — QA renders (read-only on sources/candidates; writes only qa_v3/).

Scale rule: game scale = 960/1672 horizontally and 540/941 vertically applied to the WHOLE wider
candidate (so protected objects keep the in-game size); never squeezed to 960 width.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
QA = HERE / "qa_v3"
SRC = HERE.parent / "draft_v1"
SX, SY = 960 / 1672, 540 / 941
DARK, CYAN = (26, 16, 30, 255), (38, 198, 218, 255)


def load(p):
    return Image.open(p).convert("RGBA")


def on(bg, im):
    b = Image.new("RGBA", im.size, bg); b.alpha_composite(im); return b.convert("RGB")


def game_scale(im):
    w, h = im.size
    return im.convert("RGBa").resize((round(w * SX), round(h * SY)), Image.LANCZOS).convert("RGBA")


def tile(im, n):
    w, h = im.size
    o = Image.new("RGBA", (w * n, h), (0, 0, 0, 0))
    for i in range(n):
        o.paste(im, (i * w, 0))  # raw paste: tiles do not overlap
    return o


def zoom(im, box, k):
    c = im.crop(box)
    return c.resize((c.size[0] * k, c.size[1] * k), Image.NEAREST)


def label(img, text, xy=(6, 4), fill=(255, 255, 255)):
    d = ImageDraw.Draw(img); d.rectangle([xy[0] - 3, xy[1] - 2, xy[0] + 7 * len(text), xy[1] + 12], fill=(0, 0, 0))
    d.text(xy, text, fill=fill); return img


def main() -> None:
    QA.mkdir(exist_ok=True)
    man = json.loads((HERE / "prep_manifest.json").read_text(encoding="utf-8"))
    sky = load(SRC / "01_sky.png").resize((960, 540), Image.LANCZOS)
    out = {}
    for lid, L in man["layers"].items():
        src = load(HERE.parent / L["source_file"])
        ox, oy = L["source_offset_in_candidate"]
        cw, ch = L["candidate_canvas_size"]
        for var in ("candidate", "candidate_unshifted_alt"):
            cand = load(HERE / "candidates" / f"{lid}_{var}.png")
            tag = f"{lid}_{'reg' if var == 'candidate' else 'unshifted'}"
            # (3) edit scope overlay
            sc = on(DARK, cand); d = ImageDraw.Draw(sc)
            d.rectangle([ox, oy, ox + 1671, oy + 940], outline=(0, 255, 0), width=3)
            add = np.array(cand)[..., 3] > 0
            add[oy:oy + 941, ox:ox + 1672] = False
            ov = np.array(sc); ov[add] = (ov[add] * 0.55 + np.array([255, 0, 255]) * 0.45).astype(np.uint8)
            sc = Image.fromarray(ov); d = ImageDraw.Draw(sc)
            d.rectangle([ox, oy, ox + 1671, oy + 940], outline=(0, 255, 0), width=3)
            label(sc, f"{tag}: green=protected source rect (exact RGBA), magenta tint=new image_gen pixels outside it")
            sc.save(QA / f"{tag}_edit_scope.png")
            # before/after at original scale, same coordinates
            before = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); before.paste(src, (ox, oy))
            ba = Image.new("RGB", (cw, ch * 2)); ba.paste(on(DARK, before), (0, 0)); ba.paste(on(DARK, cand), (0, ch))
            label(ba, "BEFORE draft_v1 (source coords)"); label(ba, "AFTER candidate", (6, ch + 4))
            ba.save(QA / f"{tag}_before_after.png")
            # (5) diff registered to source coords
            c = np.array(cand).astype(int); bb = np.array(before).astype(int)
            diff = np.abs(c - bb).max(axis=2)
            dv = np.zeros((ch, cw, 3), np.uint8)
            prot = np.zeros((ch, cw), bool); prot[oy:oy + 941, ox:ox + 1672] = True
            dv[prot & (diff > 0)] = (255, 0, 0)            # any change inside protection (must be none)
            dv[prot & (diff == 0)] = (0, 60, 0)              # protected & identical
            dv[~prot] = np.stack([np.array(cand)[..., 3][~prot]] * 3, -1) * np.array([1.0, 0.0, 1.0])
            Image.fromarray(dv).save(QA / f"{tag}_diff_source_coords.png")
            out.setdefault(lid, {})[var] = dict(protected_changed_pixels=int((prot & (diff > 0)).sum()),
                                               added_nonzero_alpha_pixels=int((~prot & (np.array(cand)[..., 3] > 0)).sum()))
            # (4) tiling at game scale
            gs = game_scale(cand)
            for n in (2, 3):
                t = tile(gs, n)
                for bgn, bg in (("dark", DARK), ("cyan", CYAN)):
                    im = on(bg, t)
                    if lid != "L3":
                        d = ImageDraw.Draw(im)
                        for i in range(1, n):
                            x = i * gs.size[0]; d.line([x, 0, x, 8], fill=(255, 255, 0), width=2)
                        for i in range(n):
                            x = i * gs.size[0] + round(1672 * SX); d.line([x, 0, x, 8], fill=(0, 255, 0), width=2)
                    label(im, f"{tag} x{n} game scale ({gs.size[0]}px period); yellow tick=outer seam, green tick=source/extension inner boundary")
                    im.save(QA / f"{tag}_{n}tile_{bgn}.png")
            # joins at original pixel scale (1:1 and 3x)
            joins = {}
            if lid != "L3":
                joins["inner"] = 1672            # source right edge -> extension
                joins["outer"] = cw              # extension right edge -> next tile source x=0
                t2 = tile(cand, 2)
                rows = (60, 900)
                for k, x in joins.items():
                    box = (x - 240, rows[0], x + 240, rows[1])
                    on(DARK, t2.crop(box)).save(QA / f"{tag}_join_{k}_1x_dark.png")
                    on(DARK, zoom(t2, (x - 80, 330 if lid == "L1" else 150, x + 80, 330 + 200 if lid == "L1" else 150 + 200), 3)).save(
                        QA / f"{tag}_join_{k}_3x_dark.png")
                    # 960x540 viewport in game scale centred on the join, over the real L0 sky
                    gx = round(x * SX); t2g = tile(gs, 2)
                    vp = sky.copy(); vp.alpha_composite(t2g.crop((gx - 480, 0, gx + 480, 540)))
                    vp = vp.convert("RGB"); ImageDraw.Draw(vp).line([480, 0, 480, 6], fill=(255, 255, 0), width=2)
                    vp.save(QA / f"{tag}_viewport960_{k}.png")
            else:
                for k, x, y0 in (("left_inner", 96, 600), ("right_inner", 96 + 1672, 640)):
                    on(DARK, cand.crop((x - 160, y0, x + 160, 941))).save(QA / f"{tag}_join_{k}_1x_dark.png")
                    on(CYAN, cand.crop((x - 160, y0, x + 160, 941))).save(QA / f"{tag}_join_{k}_1x_cyan.png")
                    on(DARK, zoom(cand, (x - 70, 760, x + 70, 941), 3)).save(QA / f"{tag}_join_{k}_3x_dark.png")
                # atlas slot overlay: existing rects shifted by the source offset, plus pad-inclusive suggestions
                im = on(CYAN, cand); d = ImageDraw.Draw(im)
                slots = {"ruin_left": [0, 610, 330, 331], "stones": [330, 860, 520, 81],
                         "grass": [860, 860, 460, 81], "ruin_right": [1330, 640, 342, 301],
                         "ruin_right_ext(codex)": [1240, 640, 432, 301]}
                for i, (n, (x, y, w, h)) in enumerate(slots.items()):
                    col = [(255, 255, 0), (255, 255, 255), (255, 255, 255), (255, 255, 0), (255, 128, 0)][i]
                    d.rectangle([x + ox, y + oy, x + ox + w - 1, y + oy + h - 1], outline=col, width=2)
                    d.text((x + ox + 4, y + oy + 4 + 12 * (i == 4)), n, fill=col)
                d.rectangle([ox, oy, ox + 1671, oy + 940], outline=(0, 255, 0), width=1)
                ys = np.where(np.array(cand)[..., 3] > 8)
                label(im, f"{tag} atlas: green=source rect, slots shifted +{ox}px; pads only visible if rects later include x<{ox} / x>{ox+1671}")
                im.save(QA / f"{tag}_atlas_slots.png")
    (QA / "qa_render_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
