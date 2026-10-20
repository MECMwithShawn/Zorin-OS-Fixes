"""Decode HEIC/HEIF with a private libheif runtime, with a system fallback.

Called only in the existing bounded image worker, never on the UI thread.
The returned Pillow image has no EXIF, location data or source metadata.
"""
import io
import os

EXTENSIONS = {'.heic', '.heif'}


def _decode_gdk(content, edge, pixel_limit):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    from PIL import Image
    try:
        loader = GdkPixbuf.PixbufLoader.new_with_mime_type('image/heif')
    except Exception as error:
        raise ValueError('HEIC previews require the heif-gdk-pixbuf package.') from error
    dimensions = []
    def prepared(loader, width, height):
        dimensions[:] = [width, height]
        scale = min(1, edge / max(width, height)) if width > 0 and height > 0 else 0
        loader.set_size(max(1, round(width * scale)), max(1, round(height * scale)))
    loader.connect('size-prepared', prepared)
    try:
        loader.write(content)
        loader.close()
    except Exception as error:
        try: loader.close()
        except Exception: pass
        raise ValueError('This HEIC photo could not be decoded.') from error
    if len(dimensions) != 2 or not 0 < dimensions[0] * dimensions[1] <= pixel_limit:
        raise ValueError('This image is too large to preview.')
    source = loader.get_pixbuf()
    if source is None:
        raise ValueError('This HEIC photo could not be decoded.')
    source = source.apply_embedded_orientation()
    mode = 'RGBA' if source.get_has_alpha() else 'RGB'
    picture = Image.frombytes(mode, (source.get_width(), source.get_height()),
                             source.get_pixels(), 'raw', mode, source.get_rowstride())
    picture.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    picture.info.clear()
    return picture, tuple(dimensions)


def decode(content, edge, pixel_limit):
    # Keep the current libheif wheel private to this app; the system loader
    # rejects some iPhone depth metadata and can stall under worker limits.
    from pathlib import Path
    import sys
    runtime = Path(os.environ.get('ZORIN11_HEIF_RUNTIME', str(Path(__file__).with_name('heif-runtime'))))
    if not runtime.is_dir():
        return _decode_gdk(content, edge, pixel_limit)
    if str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))
    import pillow_heif
    from PIL import Image
    pillow_heif.options.DECODE_THREADS = 1
    source = pillow_heif.open_heif(content)
    dimensions = source.size
    if not 0 < dimensions[0] * dimensions[1] <= pixel_limit:
        raise ValueError('This image is too large to preview.')
    picture = source.to_pillow()
    picture.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    picture.info.clear()
    return picture, dimensions


def png(content, edge, pixel_limit):
    picture, dimensions = decode(content, edge, pixel_limit)
    output = io.BytesIO()
    picture.save(output, format='PNG')
    return output.getvalue(), dimensions
