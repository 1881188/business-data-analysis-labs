"""Data integration and cleaning entry point."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"src"))
from bda_labs.cleaning import main
if __name__=="__main__": main()
