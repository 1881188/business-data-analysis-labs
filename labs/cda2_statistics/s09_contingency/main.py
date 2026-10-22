"""S09 independently runnable textbook migration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from bda_labs.contingency import main
if __name__=='__main__':main()
