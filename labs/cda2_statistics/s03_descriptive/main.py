"""S03 independent course experiment entry point."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from bda_labs.descriptive import main
if __name__=='__main__':main()
