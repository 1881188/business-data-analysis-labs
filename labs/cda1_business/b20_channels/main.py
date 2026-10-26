"""B20 independent entry point."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from bda_labs.channel_attribution import main
if __name__=='__main__':main()
