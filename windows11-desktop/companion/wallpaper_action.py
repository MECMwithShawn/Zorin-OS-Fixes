"""Desktop-menu wallpaper action, independent of Explorer's running process."""
import os
from pathlib import Path
import subprocess
import wallpaper


def main():
    # Present the existing controls immediately, including status/error refresh.
    subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('app.py')),
                      '--settings', 'background'], env=dict(os.environ, GDK_BACKEND='x11'))
    if wallpaper.load()['source'] in wallpaper.FEEDS:
        try:
            wallpaper.update()
        except Exception as error:
            # update() persists the error for the Settings page; keep the desktop.
            print(str(error), flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
