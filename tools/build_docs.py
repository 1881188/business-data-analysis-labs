"""Publish only explicitly selected aggregate artifacts and regenerate experiment navigation."""
from pathlib import Path
import csv,json,shutil,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bda_labs.common import ROOT,sha256,implemented_labs

PUBLIC={key:spec['public'] for key,spec in implemented_labs().items()}


def main():
    statuses={}
    for lab,files in PUBLIC.items():
        source=ROOT/"outputs"/lab
        if not source.is_dir():source=ROOT/"docs/results"/lab
        summary=json.loads((source/"summary.json").read_text(encoding="utf-8"))
        for path,digest in summary["implementation_sha256"].items():
            if sha256(ROOT/path)!=digest:raise RuntimeError(f"{lab} results are stale after editing {path}; rerun this lab")
        target=ROOT/"docs/results"/lab
        target.mkdir(parents=True,exist_ok=True)
        for name in files:
            if source.resolve()!=target.resolve():shutil.copyfile(source/name,target/name)
        statuses[lab]=summary["status"]
    config=json.loads((ROOT/"config/experiments.json").read_text(encoding="utf-8"))
    verified=[key for key,state in statuses.items() if state=='reference_verified']
    lines=["# 实验索引","",f"目前{len(statuses)}个独立实验已运行，其中{len(verified)}个完成指定参考核对（{', '.join(verified)}）。核对范围与差异见各报告。实施单元与源Notebook不是同一计数口径，不计算混合完成率。","",
        "素材覆盖：572份文件，58份Notebook、9份已有Python辅助文件、65份Excel；插件和阅读资料不按独立实验验收。所有来源见[source-map.csv](source-map.csv)。",""]
    last=None
    for item in config:
        if item["book"]!=last:
            lines += ["",f"## {item['book']}","","| ID | 实验/来源名称 | 状态 | 实现与结果 |","|---|---|---|---|"]
            last=item["book"]
        lab=item["lab_id"]
        state="参考核对通过" if statuses.get(lab)=="reference_verified" else "运行通过" if lab in statuses else item.get("status","待迁移")
        target=f"[代码](../{item['target_script']}) · [报告](results/{lab}/report.md)" if lab in statuses else item.get("note", "—")
        lines.append(f"| {lab} | {item['title']} | {state} | {target} |")
    (ROOT/"docs/experiment-index.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    mapping=ROOT/"docs/source-map.csv"
    with mapping.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream)
        fields=reader.fieldnames
        rows=list(reader)
    for row in rows:
        if row["lab_id"] in statuses:row["status"]=statuses[row["lab_id"]]
    with mapping.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
    print(f"Published {len(statuses)} aggregate result folders; source-level status updated.")


if __name__=="__main__":main()
