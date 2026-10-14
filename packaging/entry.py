"""The frozen executable uses the same application entry point as source installs."""
import sys
from wallpaper_cutter.bundle_runtime import configure, package_check

configure()
if len(sys.argv) == 3 and sys.argv[1] == '--package-check':
    sys.exit(package_check(sys.argv[2]))

from wallpaper_cutter.app import main
sys.exit(main())
