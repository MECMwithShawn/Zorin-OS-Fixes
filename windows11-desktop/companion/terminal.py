#!/usr/bin/python3
"""XFCE terminal helper: preserve arguments without evaluating shell strings."""
import os
from pathlib import Path
import sys


def command(args, home):
    argv = [str(home/'.local/bin/wezterm'), 'start']
    if args:
        argv += ['--', *args]
    return argv


if __name__ == '__main__':
    argv = command(sys.argv[1:], Path.home())
    os.execv(argv[0], argv)
