"""Compare frozen route pixels to the corresponding route-off frames."""
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

def measure(folder,name,anchors=None):
    def load(file):
        with Image.open(folder/file) as src:
            arr=np.array(src.convert('RGB'),dtype=np.float32)
        h,w=arr.shape[:2]
        return arr[h//2-max(8,h//35):h//2+max(8,h//35),w//4:3*w//4,:]
    images=np.stack([load(f'{name}-{i}.png') for i in range(10)])
    background=(np.stack([load(f'{name}-off-{i}.png') for i in range(10)]) if anchors
                else load(f'{name}-off.png'))
    # Ground textures, shadows and geometry already present in the background
    # must not dilute the variance observed on the actual drawn blue dashes.
    signal=(images[...,2]-images[...,0])-(background[...,2]-background[...,0])
    if anchors:
        # Register the straight route back to its starting ground coordinates.
        # Remove the crop edges that move into frame during the pan.
        for i,x in enumerate(anchors):
            offset=x-anchors[0];left=int(np.floor(offset));fraction=offset-left
            signal[i]=(1-fraction)*np.roll(signal[i],-left,axis=1)+fraction*np.roll(signal[i],-left-1,axis=1)
        trim=int(np.ceil(max(abs(x-anchors[0]) for x in anchors)))+1
        signal=signal[:,:,trim:-trim]
    route=signal.mean(axis=0)>12.
    assert route.sum()>60,(folder,name,route.sum(),float(signal.max()))
    dif=np.abs(np.diff(signal[:,route],axis=0))
    return dict(pixels=int(route.sum()),mean_blue_chroma_gain=float(signal[:,route].mean()),
                mean_frame_difference=float(dif.mean()),p95_frame_difference=float(np.percentile(dif,95)),
                percent_changes_over_8=float(100.*np.mean(dif>8)))

if __name__=='__main__':
    for arg in sys.argv[1:]:
        folder=Path(arg)
        record={name:measure(folder,name) for name in ('near','far')}
        anchors=json.loads((folder/'verification.json').read_bytes())['states'].get('pan_anchor_pixels')
        if anchors:record['moving_camera']=measure(folder,'pan',anchors)
        (folder/'pixel_measurements.json').write_text(json.dumps(record,indent=2),encoding='utf8')
        print(folder.name,record)
