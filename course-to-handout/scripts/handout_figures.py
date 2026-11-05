"""Figure candidate hints and reproducible crops. Similarity never deletes evidence."""
from pathlib import Path

from handout_core import HandoutError, read_json, write_json, within, file_hash, digest


def candidates(job,unit_id=None):
    from PIL import Image
    job=Path(job);frames=read_json(job/'materials/frames.json');rows=[]
    for f in frames:
        p=within(job,f['path'])
        with Image.open(p) as image:
            # Candidate signal only: small symbol changes may have almost equal hashes.
            small=image.convert('L').resize((9,8));pixels=[small.getpixel((x,y)) for y in range(8) for x in range(9)]
            bits=''.join('1' if pixels[y*9+x]>pixels[y*9+x+1] else '0' for y in range(8) for x in range(8))
            rows.append({'frame_id':f['id'],'time':f['time'],'dhash':f'{int(bits,2):016x}','width':image.width,'height':image.height})
    pairs=[]
    for a,b in zip(rows,rows[1:]):
        distance=(int(a['dhash'],16)^int(b['dhash'],16)).bit_count()
        pairs.append({'frames':[a['frame_id'],b['frame_id']],'time_gap':b['time']-a['time'],'hash_distance':distance,
                      'decision':'review_information_increment','instruction':'核对小面积符号变化、纠错、擦除前独有内容；不能据相似度自动删除'})
    result={'unit_id':unit_id,'frames':rows,'neighbor_pairs':pairs,'auto_deleted':0,'threshold':'none; calibrate on labelled course material'}
    write_json(job/'figure-candidates.json',result);return result


def crop_figure(job,figure,frames,destination):
    from PIL import Image
    frame=next(f for f in frames if f['id']==figure['frame_id'])
    source=within(job,frame['path']);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    name=digest({'source':file_hash(source),'crop':figure.get('crop')})+'.png';output=destination/name
    with Image.open(source) as image:
        crop=figure.get('crop')
        if crop:
            x,y,w,h=crop
            if x<0 or y<0 or w<=0 or h<=0 or x+w>image.width or y+h>image.height:raise HandoutError(f'CROP_BOUNDS: {figure["id"]} 超出原帧像素范围')
            image=image.crop((x,y,x+w,y+h))
        image.convert('RGB').save(output)
    return output
