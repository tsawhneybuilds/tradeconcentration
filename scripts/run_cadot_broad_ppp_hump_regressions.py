#!/usr/bin/env python3
"""Cadot broad 156-country PPP hump regression entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_ppp_hump_regressions as ppp  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-ppp", action="store_true", help="Refresh World Bank PPP and population controls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    argv = [
        "--country-sample",
        ppp.CADOT_BROAD_SAMPLE,
        "--start-year",
        str(ppp.CADOT_BROAD_START_YEAR),
        "--end-year",
        str(ppp.CADOT_BROAD_END_YEAR),
    ]
    if args.refresh_ppp:
        argv.append("--refresh-ppp")
    ppp.main(argv)


if __name__ == "__main__":
    main()
