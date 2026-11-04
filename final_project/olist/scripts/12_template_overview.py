"""Compose ten Python figures into a numbered template overview, not new charts."""
from pathlib import Path
import csv,json,hashlib
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/template_overview'
REFERENCE=[
 ('01','1 渐变柱形图','渐变柱形图','fig01'),
 ('02','2 带均值柱形图','带均值柱形图','fig02'),
 ('03','3 渐变圆角柱形图','渐变圆角柱形图','fig03'),
 ('06','6 蝴蝶图','蝴蝶图','fig04'),
 ('08','8 数值百分比','数值与百分比','fig05'),
 ('11','11 平滑折线图','平滑折线图','fig06'),
 ('13','13 对比折线图','对比折线图','fig07'),
 ('19','19 南丁格尔圆饼图','圆饼图','fig08'),
 ('20','20 南丁格尔圆环图','分层圆环图','fig09'),
 ('26','26 柱形圆','柱形圆','fig10'),
]


def main():
    import os
    OUT.mkdir(parents=True,exist_ok=True)
    font=os.environ.get('OLIST_CHINESE_FONT','C:/Windows/Fonts/msyh.ttc')
    label=ImageFont.truetype(font,42);title=ImageFont.truetype(font,51)
    small=ImageFont.truetype(font,29)
    rows=list(csv.DictReader((ROOT/'outputs/tables/figure_index.csv').open(encoding='utf-8-sig')))
    byid={r['figure']:r for r in rows}
    canvas=Image.new('RGB',(2400,3770),'#1B2043');draw=ImageDraw.Draw(canvas)
    draw.text((48,25),'10种可视化模板复现总览',font=title,fill='#F1F3FA')
    entries=[]
    for i,(number,sheet,name,fig) in enumerate(REFERENCE):
        row=byid[fig];assert row['template']==number
        x=36+(i%2)*1182;y=110+(i//2)*716
        draw.text((x+12,y+4),f'模板{number}  {name}  {fig}',font=label,fill='#F1F3FA')
        source=ROOT/'outputs/figures'/row['filename']
        image=Image.open(source).convert('RGB');image=image.resize((1152,648),Image.Resampling.LANCZOS)
        canvas.paste(image,(x,y+62))
        entries.append({'template':number,'reference_workbook':'第二章 图表(前15).xlsx' if int(number)<=15 else '第二章 图表(后15).xlsx',
                        'reference_sheet':sheet,'figure':fig,'filename':row['filename'],'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    draw.text((48,3705),'数据：Olist；全部为Python生成；缩略图索引，详细数值与口径见正文及独立原图。',font=small,fill='#C4CADE')
    assert len({e['template'] for e in entries})==10
    canvas.save(OUT/'template_overview_10.png',dpi=(300,300))
    manifest={'unique_templates':10,'selected_original_figures':10,'new_independent_charts':0,
              'data_source':'Olist; chart style references are the supplied Excel worksheets',
              'entries':entries}
    (OUT/'template_overview_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('10-template overview saved; original chart count remains 15')


if __name__=='__main__':main()
