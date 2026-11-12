"""Read-only: alpha/luma profile along source edge columns, for constraint analysis."""
import json, numpy as np
from PIL import Image
D='game/assets/backgrounds/twilight_ruins/'
O=D+'candidates_v4/prep/'
def comp(a,bg=(28,18,32)):
    c=a.astype(float); al=c[...,3:4]/255
    return (c[...,:3]*al+np.array(bg,float)*(1-al)).astype(np.uint8)
def zoom(img,k): return Image.fromarray(img).resize((img.shape[1]*k,img.shape[0]*k),Image.NEAREST)
res={}
for k,f,crops in [
 ('L1','02_far_castle.png',[('right_wall',1592,1672,300,440,6),('right_fog',1592,1672,430,670,4),('left_fog',0,80,560,670,6)]),
 ('L2','03_mid_invasion.png',[('right',1572,1672,430,670,4),('left_top',0,100,150,330,4),('left_low',0,100,500,670,4)]),
 ('L3','04_near_debris.png',[('left',0,100,640,941,3)])]:
    a=np.array(Image.open(D+'draft_v1/'+f).convert('RGBA'))
    for n,x0,x1,y0,y1,z in crops:
        zoom(comp(a[y0:y1,x0:x1]),z).save(O+f'{k}_srczoom_{n}_x{x0}-{x1}_y{y0}-{y1}_{z}x.png')
    prof={}
    for x in (0,1671):
        col=a[:,x]; rows=[]
        for y in range(0,941,4):
            if col[y,3]>0: rows.append([y,int(col[y,3]),int(col[y,:3].astype(int).mean())])
        prof[f'x{x}']=rows
    res[k]=prof
json.dump(res,open(O+'source_edge_profiles_alpha_luma_step4.json','w'))
r=res['L1']['x1671']; print('L1 x1671', r[:6], r[-6:])
print('L1 x0', res['L1']['x0'])
