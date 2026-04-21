#!/usr/bin/env python3
"""Compatibility entrypoint for redirect validation in docs CI."""

from __future__ import annotations

import sys

from check_redirects import main


if __name__ == "__main__":
    sys.exit(main())
