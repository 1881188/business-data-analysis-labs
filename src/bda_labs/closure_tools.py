"""Audit sparse Excel chart caches without treating missing points as zero."""
from xml.etree import ElementTree as ET
import re,zipfile
import pandas as pd
from .common import compare_numeric


def chart_caches(path,book,destinations):
    ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'};rows=[]
    with zipfile.ZipFile(path) as z:
        names=sorted([n for n in z.namelist() if re.fullmatch(r'xl/charts/chart\d+\.xml',n)],key=lambda s:int(re.search(r'chart(\d+)',s)[1]))
        if len(names)!=len(destinations):raise AssertionError('Every chart requires a destination')
        for name,destination in zip(names,destinations):
            for number,series in enumerate(ET.fromstring(z.read(name)).findall('.//c:ser',ns),1):
                val=series.find('c:val',ns);ref=val.find('.//c:f',ns)
                if ref is None:raise ValueError('Review chart literal series explicitly')
                sheet,area=ref.text.rsplit('!',1);sheet=sheet.strip("'").replace("''", "'")
                values=[v for row in book[sheet].matrix(area.replace('$','')) for v in row]
                points=val.findall('.//c:pt',ns)
                for point in points:
                    index=int(point.attrib['idx']);saved=float(point.find('c:v',ns).text)
                    if index>=len(values) or values[index] is None:raise AssertionError('Chart point has no corresponding source cell')
                    compare_numeric([saved],[values[index]],f'{name}/{number}/{index}')
                rows.append({'chart':name,'series':number,'value_reference':ref.text,'range_positions':len(values),
                             'cached_numeric_points':len(points),'sparse_positions':len(values)-len(points),
                             'cached_values_match_cells':True,'python_destination':destination})
    return pd.DataFrame(rows)
