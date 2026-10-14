#!/usr/bin/env python3
"""Launch directly from a source checkout without installing Python packages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from wallpaper_cutter.app import main

if __name__ == '__main__':
    sys.exit(main())
