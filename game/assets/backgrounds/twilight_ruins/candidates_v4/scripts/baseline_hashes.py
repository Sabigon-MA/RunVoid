"""Record sha256 of every file in the repo work tree (excluding .git and candidates_v4) at task start / end."""
import hashlib, json, os, sys, pathlib
root = sys.argv[1]; out = sys.argv[2]
res = {}
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d not in ('.git', '__pycache__', 'candidates_v4')]
    for f in fn:
        p = os.path.join(dp, f)
        rel = pathlib.PurePath(os.path.relpath(p, root)).as_posix()
        with open(p, 'rb') as fh:
            res[rel] = hashlib.sha256(fh.read()).hexdigest()
json.dump(res, open(out, 'w'), indent=0, sort_keys=True)
print(len(res))
