"""Run the implemented pipeline; --from-stage allows resuming completed work."""
from pathlib import Path
import argparse
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--from-stage',type=int,choices=range(1,12),default=1)
args = parser.parse_args()
stages = ['01_download.py','02_profile.py','03_clean.py','04_analysis.py','05_forecast.py','06_preview.py','07_report.py','08_visuals.py','09_verify_figures.py','10_dashboard_check.py','11_paper_panels.py']
for stage in stages[args.from_stage-1:]:
    subprocess.run([sys.executable, str(root / 'scripts' / stage)], check=True)
