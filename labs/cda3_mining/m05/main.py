"""Run M05 from the repository root or any working directory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from bda_labs.advanced_profiles import main

if __name__ == "__main__":
    main("M05")
