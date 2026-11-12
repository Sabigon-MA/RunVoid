"""Build final_candidate_manifest.json for coordinator QA (reads reports; writes only candidates_v4)."""
import hashlib, json
D = 'game/assets/backgrounds/twilight_ruins/'
V4 = D + 'candidates_v4/'
A = json.load(open(V4 + 'assemble_report_v4.json'))
P = json.load(open(V4 + 'prep_manifest_v4.json'))
V3M = json.load(open(D + 'candidates_v3/final_candidate_manifest.json', encoding='utf-8'))
Q = json.load(open(V4 + 'qa_v4/qa_v4_summary.json'))


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def gate(g):
    return 'PASS' if g['pass'] else 'FAIL'


VIS = {
    'L1': {'inner_x1672': 'FAIL (visual): haze bottom ends ~row 625 vs source fade to 646 -> dark notch; luminous haze value step; vertical cut visible at 1x/4x',
           'outer_wrap': 'FAIL (visual): generated band ends as a pointed opaque-ish wedge (a>=8 rows 591..624) against source faint fog (rows 600..642, alpha<=39); hard step',
           'composition': 'IMPROVED vs v3: no ruin stubs/architecture added; only hill/haze. Cathedral/towers/bridge exact bytes.'},
    'L2': {'inner_x1672': 'FAIL (visual): rectangular pad block, flat bottom ~row 675 (source 636) -> 40px step; L0 red sky visible below in cam1200; new small ruins (arched wall, pillars) drawn despite instruction',
           'outer_wrap': 'FAIL (visual + structural): rib lattice cut vertically at the seam (pad a>=128 starts row 390 vs source 175). Predicted constraint conflict: source x0 carries a ~480px-tall cut rib cross-section; a seamless join needs equally tall new rib structure, which the no-new-architecture rule forbids',
           'composition': 'Partly improved vs v3 (no new peaked arch) but new small ruin forms -> violates no-new-architecture'},
    'L3': {'left_inner_x96': 'FAIL (gates G3; visual partial): SAME boulder now continues at source contact height (big improvement vs v3 ~40px lower separate rock) and closes at the far left; but dense dry-grass clump ends vertically at the join, generated grass is sparse -> visible density step at 1x/4x; lit top edge slightly flatter/brighter',
           'right_inner_x1768_HELD_v3': 'HELD (unchanged v3 pixels, provenance raw copy). Visual PASS as in v3; note predeclared a8 contour gate flags grass tips (21px) — gate is strict on sparse grass',
           'composition': 'Source rocks/grass/tree exact bytes; pads only; not visible in game without src-rect change (not done)'},
}

out = {'schema': 'runvoid.bg.candidates_v4/1', 'adopted': False, 'connected_to_game_config': False,
       'overall': 'NOT ACCEPTED. Protected-source exactness PASS (0 changed pixels, all layers). All newly generated joins FAIL predeclared gates; '
                  'L3-left is the closest (correct boulder height) but has a grass-density cut. L2 outer seam is a structural constraint conflict. '
                  'L3-right remains HELD v3 partial candidate.',
       'scale_rule': 'game scale 960/1672 x, 540/941 y on the whole candidate; never squeezed to 960 width; offsets/ground level as v3/original',
       'geometry_change_vs_v3': 'none (same canvas sizes/offsets/pad widths; v4 masks pixel-identical to v3 masks)',
       'strategy_change_vs_v3': ['local crops: 128px context instead of 546px full-height; row band only',
                                 'explicit guides (contour/forbid/stub zone) only on new pixels, reference-only',
                                 'L1 fog-only job (v3 prompt had wrongly described a cut window); L2 low rubble + <=72px rib stubs; L3 same-boulder',
                                 'registration limited to +-3px and only if both sides agree; predeclared numeric gates; no blending'],
       'acceptance_gates_predeclared': P['acceptance_gates_predeclared'],
       'tool_limits': 'built-in image_gen (coordinator-run, one call per job): no enforced mask, no size parameter (L2 returned 1254x1254); context regenerated in all jobs (L1 dropped the cathedral from context: left-side registration error 99)',
       'layers': {}}
for L in ('L1', 'L2', 'L3'):
    a = A[L]; pr = P['protection'][L]; v3 = V3M['layers'][L]
    jobs = {k: a[k] for k in a if k in P['jobs']}
    joins = {}
    for jn, g in a['gates'].items():
        if jn.startswith('G5'):
            continue
        joins[jn] = {'G3_contour': gate(g['G3_contour']), 'G4_value': gate(g['G4_value']),
                     'G4_ratio': g['G4_value']['ratio'], 'detail': g, 'visual': VIS[L].get(jn, ''),
                     'verdict': 'HELD (v3)' if 'HELD' in jn else 'FAIL'}
    out['layers'][L] = {
        'candidate_file': a['candidate_file'], 'candidate_sha256': sha(V4 + a['candidate_file']),
        'status': 'REJECTED_JOIN_FAIL' if L != 'L3' else 'REJECTED left pad (FAIL); right pad HELD v3 partial',
        'canvas_size': a['canvas_size'], 'source_offset': a['source_offset'], 'source_size': a['source_size'],
        'source_file': pr['source_file'], 'source_sha256': pr['source_sha256'],
        'source_sha256_after': a['protection_equality_proof']['source_sha256_after'],
        'protection_mask': pr['file'], 'protection_mask_sha256_predeclared': pr['sha256'],
        'protection_mask_sha256_after': sha(V4 + pr['file']),
        'protection_mask_identical_to_v3': pr['identical_to_v3_mask_pixels'], 'v3_mask_sha256': pr['v3_mask_sha256'],
        'protection_equality_proof': a['protection_equality_proof'],
        'generation': jobs, 'G5_forbidden_zone': a['gates']['G5_forbidden_zone'], 'joins': joins,
        'composition': VIS[L]['composition'], 'alpha_stats': Q[L],
        'v3_to_v4_delta': {'v3_candidate_sha256': v3['candidate_sha256'], 'v3_status': v3['acceptance']['status'],
                           'geometry': 'unchanged', 'protected_region': 'identical bytes in both'},
        'qa_files': sorted([f'qa_v4/{f}' for f in __import__('os').listdir(V4 + 'qa_v4') if f.startswith(L + '_')]),
    }
    if L == 'L3':
        out['layers'][L]['L3_right_held'] = a['L3_right_held']
out['integration_qa'] = {'adapter': 'scripts/integration_v4.py (imports Codex render_integration.candidate_profile read-only, writes qa_v4/integration only)',
                         'profiles': ['current_draft_v1', 'v3_all_unapproved', 'v4_all_REJECTED_unapproved'],
                         'cameras': [0, 600, 1200, 1600, 2240], 'wrap_frames': 'L1/L2 period boundary +0/-60, inner join centred',
                         'observed': 'cam1200: L2 pad block with flat bottom exposes L0 red sky band; L1 pad haze notch; protagonist/enemies/HUD readable in stills'}
out['verification_scope'] = {'visually_inspected': ['raw outputs', 'L1/L2/L3 joins 1x+4x original/v3/v4', 'L1/L2 2-tile', 'L3 alpha check 4 bgs', 'v4 cam1200 integration'],
                             'generated_not_individually_viewed': 'remaining tile/alpha/cam images were generated deterministically for coordinator QA',
                             'untested': ['native window', 'DPI 100/125/150%', 'real 60FPS', 'human dynamic play']}
json.dump(out, open(V4 + 'final_candidate_manifest.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('ok')
