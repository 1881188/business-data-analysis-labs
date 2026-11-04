"""Check figure counts, metadata, assets and package the chart milestone."""
from pathlib import Path
import csv
import json
import hashlib
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'


def main():
    with (OUT/'tables/figure_index.csv').open(encoding='utf-8-sig',newline='') as f:
        index=list(csv.DictReader(f))
    assert len(index)==15
    assert len({x['figure'] for x in index})==15
    templates={x['template'] for x in index if x['template']!='新增业务图'}
    assert templates=={'01','02','03','06','08','11','13','19','20','26'}
    methods={x['method'] for x in index}
    assert {'趋势1','趋势2','ABC1','ABC2','预测1','预测2'}<=methods
    hashes=[]
    sizes=[]
    for row in index:
        p=OUT/'figures'/row['filename']
        with Image.open(p) as im:
            assert im.size==(1920,1080),p
            assert min(im.info['dpi'])>=150,p
            im.verify()
        hashes.append(hashlib.sha256(p.read_bytes()).hexdigest())
        sizes.append(p.stat().st_size)
    assert len(set(hashes))==15,'Duplicated chart files'
    layout=json.loads((OUT/'tables/figure_layout_checks.json').read_text(encoding='utf-8'))
    assert len(layout)==15 and all(not x['text_outside_canvas'] for x in layout)
    result={'independent_chart_count':15,'distinct_reference_templates':10,
            'business_model_charts':6,'supplementary_delivery_charts':2,
            'size_pixels':[1920,1080],'dpi_minimum':150,
            'png_decode_and_integrity':'passed','duplicate_image_hashes':0,
            'canvas_text_bounds':'passed','total_png_bytes':sum(sizes),
            'manual_review':'All figures inspected in contact sheets; corrected charts inspected individually. See docs/05_图表索引与解读.md.'}
    (OUT/'tables/figure_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with ZipFile(OUT/'Olist图表包.zip','w',compression=ZIP_DEFLATED) as z:
        for row in index:
            z.write(OUT/'figures'/row['filename'],arcname='figures/'+row['filename'])
        z.write(ROOT/'docs/05_图表索引与解读.md',arcname='图表索引与解读.md')
        z.write(OUT/'tables/figure_index.csv',arcname='figure_index.csv')
        z.write(OUT/'tables/figure_verification.json',arcname='figure_verification.json')
    with ZipFile(OUT/'Olist图表包.zip') as z:
        assert z.testzip() is None
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
