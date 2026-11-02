"""Desktop-menu wallpaper actions, independent of Explorer's running process."""
import subprocess
import sys
import wallpaper


def notify(title, body=''):
    try:subprocess.run(['notify-send','--app-name=Desktop background','--icon=preferences-desktop-wallpaper',title,body],timeout=5)
    except (OSError,subprocess.SubprocessError):pass


def main(direction='next'):
    try:
        entry=wallpaper.step(direction)
    except Exception as error:
        # update() also keeps the error for the Settings page.
        print(str(error), flush=True)
        notify('Couldn\u2019t change the desktop background', str(error))
        return 1
    if entry is None:
        notify('No earlier background' if direction=='previous' else 'No newer background',
               'Turn on Bing or Windows Spotlight in Personalization to get new pictures.' if direction=='next' else '')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:2]))
