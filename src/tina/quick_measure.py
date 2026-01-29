#!/usr/bin/env python3
"""
Quick Measure - HP E5071B VNA
Wrapper script that automatically runs measurement with --now flag.
"""

import sys

from .main import main


def quick_main():
    """Main entry point for quick measure executable."""
    # Force --now argument
    sys.argv = ["hp-e5071b-quick"] + ["--now"] + sys.argv[1:]
    return main()


if __name__ == "__main__":
    sys.exit(quick_main())
