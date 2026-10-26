"""B11 independent course experiment entry point."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from bda_labs.retail_dashboard import main
if __name__=='__main__':main()
