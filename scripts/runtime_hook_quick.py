"""
Runtime hook for tina-quick executable.
Automatically adds --now flag to arguments.
"""

import sys

# Insert --now after the program name
if len(sys.argv) == 1 or "--now" not in sys.argv:
    sys.argv.insert(1, "--now")
