"""S13 standalone textbook migration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"src"))
from bda_labs.city_hierarchy import main
if __name__=="__main__":main()
