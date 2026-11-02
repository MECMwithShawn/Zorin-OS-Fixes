"""Save PNG or JPG copies of pictures beside the originals (Explorer and GNOME Files "Convert to").

Originals are never changed or replaced. Copies carry no EXIF, location data or
other source metadata, like the existing previews. HEIC/HEIF goes through
heif_images, so it uses the same private libheif runtime.
"""
import io
import os
import sys
from pathlib import Path

import heif_images

FORMATS = {'png': ('PNG', '.png'), 'jpg': ('JPEG', '.jpg')}
SOURCES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff'} | heif_images.EXTENSIONS
PIXEL_LIMIT = 200_000_000
FULL_SIZE = 1 << 20


def convertible(path):
    p = Path(path)
    return p.suffix.lower() in SOURCES and p.is_file()


def target(source, suffix):
    """A free name beside source: photo.png, then photo (2).png, and so on."""
    candidate, number = source.with_suffix(suffix), 2
    while candidate.exists():
        candidate, number = source.with_name(f'{source.stem} ({number}){suffix}'), number + 1
    return candidate


def load(source):
    if source.suffix.lower() in heif_images.EXTENSIONS:
        return heif_images.decode(source.read_bytes(), FULL_SIZE, PIXEL_LIMIT)[0]
    from PIL import Image, ImageOps
    with Image.open(source) as opened:
        if not 0 < opened.width * opened.height <= PIXEL_LIMIT:
            raise ValueError(f'{source.name} is too large to convert.')
        picture = ImageOps.exif_transpose(opened)
        picture.load()
    picture.info.clear()
    return picture


def encode(picture, kind):
    from PIL import Image
    if kind == 'JPEG' and picture.mode != 'RGB':
        rgba = picture.convert('RGBA')
        picture = Image.new('RGB', rgba.size, 'white')
        picture.paste(rgba, mask=rgba.getchannel('A'))
    elif kind == 'PNG' and picture.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA', 'I;16'):
        picture = picture.convert('RGBA' if 'A' in picture.getbands() else 'RGB')
    output = io.BytesIO()
    picture.save(output, format=kind, **({'quality': 92, 'optimize': True} if kind == 'JPEG' else {}))
    return output.getvalue()


def convert(paths, fmt):
    """Convert each picture in paths to fmt ('png' or 'jpg'); returns the new files.

    Folders, other file types and pictures already in fmt are skipped.
    """
    if fmt not in FORMATS:
        raise ValueError('Choose PNG or JPG.')
    kind, suffix = FORMATS[fmt]
    same = {'.jpg', '.jpeg'} if fmt == 'jpg' else {suffix}
    sources = [Path(p).absolute() for p in paths if isinstance(p, str) and convertible(p)]
    sources = [s for s in sources if s.suffix.lower() not in same]
    if not sources:
        raise ValueError(f'Choose pictures that aren\'t already {fmt.upper()}.')
    created = []
    for source in sources:
        try:
            data = encode(load(source), kind)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f'{source.name} could not be converted.') from error
        destination = target(source, suffix)
        with open(destination, 'xb') as handle:
            handle.write(data)
        created.append(str(destination))
    return created


def main(argv):
    """python3 image_convert.py png|jpg FILE... (used by the GNOME Files menu)."""
    if len(argv) < 2:
        print(main.__doc__, file=sys.stderr)
        return 2
    # Load Pillow from the private HEIF runtime, as heif_images would, before
    # a non-HEIC file imports the system copy first.
    runtime = Path(os.environ.get('ZORIN11_HEIF_RUNTIME', str(Path(__file__).with_name('heif-runtime'))))
    if runtime.is_dir() and 'PIL' not in sys.modules:
        sys.path.insert(0, str(runtime))
    try:
        for path in convert(argv[1:], argv[0]):
            print(path)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
