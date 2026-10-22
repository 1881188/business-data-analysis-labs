"""Produce local, non-executing Python reading drafts; this is not experiment acceptance."""
from pathlib import Path
import ast,csv,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bda_labs.common import ROOT,context,sha256,write_json


def render_notebook(notebook,source_id,relative_path):
    header=[
        '"""本地Notebook初始导出稿，保留教材说明，仅供阅读和重构。',
        '语法可解析不代表实验通过。默认启动不会执行源代码；不要把此稿当作已验收实现。',
        '原始资源许可与来源不因格式导出而改变。',
        f'来源编号：{source_id}',f'来源文件：{relative_path}',
        '"""','', 'def notebook_reference():',
        '    """Unreviewed source logic. Never invoked by this export automatically."""']
    issues=[]
    any_code=False
    for number,cell in enumerate(notebook.get('cells',[]),1):
        text=''.join(cell.get('source',[]))
        header += ['',f"    # %% cell {number} [{cell.get('cell_type','unknown')}]"]
        if cell.get('cell_type')!='code':
            header.extend('    # '+line for line in text.splitlines())
            continue
        any_code=any_code or bool(text.strip())
        processed=[]
        for line in text.splitlines():
            if line.lstrip().startswith(('%','!')) or 'get_ipython(' in line:
                processed.append('# NOTEBOOK-ONLY: '+line)
                issues.append({'cell':number,'kind':'notebook_only_line_commented'})
            else:processed.append(line)
        converted='\n'.join(processed)
        try:ast.parse(converted)
        except SyntaxError as e:
            issues.append({'cell':number,'kind':'source_syntax_requires_review','line':e.lineno,'message':e.msg})
            header.append(f'    raise NotImplementedError("Review original code cell {number}; source syntax is preserved as comments below.")')
            header.extend('    # ORIGINAL: '+line for line in text.splitlines())
        else:header.extend('    '+line if line else '' for line in processed)
    if not any_code:header.append('    pass')
    header += ['', 'if __name__ == "__main__":',
        '    raise SystemExit("Initial source export only: not independently reviewed or executed. Use a verified lab entry instead.")','']
    output='\n'.join(header)
    ast.parse(output)
    return output,issues


def main(argv=None):
    ctx=context('notebook_exports',argv)
    with (ROOT/'docs/source-map.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=[r for r in csv.DictReader(stream) if r['source_file'].endswith('.ipynb')]
    manifest=[]
    for row in rows:
        path=ctx.data_root/row['source_file']
        if sha256(path)!=row['source_sha256']:raise ValueError(f"Source changed: {row['source_id']}")
        nb=json.loads(path.read_text(encoding='utf-8-sig'))
        code,issues=render_notebook(nb,row['source_id'],row['source_file'])
        target=ctx.output/f"{row['source_id']}.py"
        target.write_text(code,encoding='utf-8')
        manifest.append({'source_id':row['source_id'],'source_file':row['source_file'],
            'target_file':target.name,'source_sha256':row['source_sha256'],'export_sha256':sha256(target),
            'status':'reading_draft_not_executed','syntax_parse_ok':True,'issues':issues})
    write_json(ctx.output/'manifest.json',manifest)
    readme=['# Notebook本地Python阅读稿','',f'共{len(manifest)}份。仅初始导出，未执行原代码，不计入已验收实验。',
            '教材Markdown保留为注释，Notebook指令标注为NOTEBOOK-ONLY；原语法问题保留为注释并插入待处理异常。',
            '每份文件默认启动都会停止，不会自动连接数据库、读取原作者绝对路径或执行源逻辑。',
            '这些文件只在本地outputs中保存，不加入公开仓库。已独立实现并验证的实验以labs/为准。','',
            '| 来源编号 | 阅读稿 | 原文件 | 待查标记数 |','|---|---|---|---:|']
    for row in manifest:readme.append(f"| {row['source_id']} | [{row['target_file']}]({row['target_file']}) | {row['source_file']} | {len(row['issues'])} |")
    (ctx.output/'README.md').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    print(f"Exported {len(manifest)} syntax-checked reading drafts. Original code was NOT executed.")


if __name__=='__main__':main()
