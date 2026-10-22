"""Run implemented labs in independent Python processes; failures are never treated as success."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
LABS={key:spec['entry'] for key,spec in json.loads((ROOT/'config/implemented_labs.json').read_text(encoding='utf-8')).items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab",nargs="+",choices=["all",*LABS],default=["all"])
    parser.add_argument("--data-root",type=Path)
    parser.add_argument("--output-root",type=Path)
    args=parser.parse_args()
    selected=list(LABS) if "all" in args.lab else list(dict.fromkeys(args.lab))
    for lab_id in selected:
        command=[sys.executable,str(ROOT/LABS[lab_id])]
        if args.data_root is not None: command += ["--data-root",str(args.data_root.resolve())]
        if args.output_root is not None: command += ["--output-root",str(args.output_root.resolve())]
        print(f"Running {lab_id}",flush=True)
        subprocess.run(command,check=True)


if __name__=="__main__": main()
