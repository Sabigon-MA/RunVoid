"""Read-only measurement of source edge columns (alpha runs) for L1/L2/L3 + make zoom crops of source edges."""
import json, sys, numpy as np
from PIL import Image
D='game/assets/backgrounds/twilight_ruins/'
out=D+'candidates_v4/prep/'
def runs(col):
    m=col>0; r=[];s=None
    for i,v in enumerate(m):
        if v and s is None: s=i
        if not v and s is not None: r.append([s,i-1]); s=None
    if s is not None: r.append([s,len(m)-1])
    return r
rep={}
for k,f in [('L1','02_far_castle.png'),('L2','03_mid_invasion.png'),('L3','04_near_debris.png')]:
    a=np.array(Image.open(D+'draft_v1/'+f).convert('RGBA'))
    rep[k]={}
    for x in [0,1,2,4,8,1663,1667,1669,1670,1671]:
        rep[k][f'x{x}']=runs(a[:,x,3])
    # crops 1x of edges with dark bg composite
    for name,x0,x1 in [('left',0,200),('right',1472,1672)]:
        c=a[:,x0:x1].astype(float); al=c[...,3:4]/255
        bg=np.array([28,18,32.]); comp=(c[...,:3]*al+bg*(1-al)).astype(np.uint8)
        Image.fromarray(comp).save(out+f'{k}_source_edge_{name}_1x_dark.png')
json.dump(rep,open(out+'source_edge_alpha_runs.json','w'),indent=1)
for k in rep:
    print(k,{x:rep[k][x] for x in ['x0','x1671']})
