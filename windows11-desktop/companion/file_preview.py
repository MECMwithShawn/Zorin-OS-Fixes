"""Bounded, read-only file previews. Never execute documents or load URLs."""
import base64
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

TEXT = {'.txt','.md','.rst','.log','.csv','.tsv','.json','.yaml','.yml','.toml',
        '.ini','.cfg','.conf','.xml','.html','.css','.js','.jsx','.ts','.tsx',
        '.py','.sh','.c','.h','.cpp','.rs','.sql','.desktop'}
IMAGES = {'.png','.jpg','.jpeg','.webp','.gif','.bmp','.heic','.heif'}
TEXT_LIMIT = 1024 * 1024
IMAGE_LIMIT = 10 * 1024 * 1024
PIXEL_LIMIT = 25_000_000


def unavailable(message):
    return {'kind':'unavailable','message':message}


def generate(path):
    p = Path(path)
    image = p.suffix.lower() in IMAGES
    if not image and p.suffix.lower() not in TEXT:
        return unavailable('No preview available for this file type.')
    # O_NONBLOCK prevents special files such as FIFOs from hanging on open.
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            return unavailable('Only regular files can be previewed.')
        limit = IMAGE_LIMIT if image else TEXT_LIMIT
        if info.st_size > limit:
            return unavailable(f'Preview is limited to {limit // 1024 // 1024} MB files.')
        content = stream.read(limit + 1)
    if len(content) > limit:
        return unavailable('This file is too large to preview.')
    if image and p.suffix.lower() in ('.heic', '.heif'):
        from heif_images import png
        try: data, (width, height) = png(content, 1024, PIXEL_LIMIT)
        except ValueError as error: return unavailable(str(error))
        return {'kind':'image', 'image':'data:image/png;base64,'+base64.b64encode(data).decode(),
                'width':width, 'height':height}
    if image:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in ('PNG','JPEG','WEBP','GIF','BMP'):
                return unavailable('No preview available for this image format.')
            if source.width * source.height > PIXEL_LIMIT:
                return unavailable('This image is too large to preview.')
            width,height = source.size
            picture = ImageOps.exif_transpose(source)
            picture.thumbnail((1024,1024))
            picture = picture.convert('RGBA')
            output = io.BytesIO();picture.save(output,format='PNG')
        return {'kind':'image','image':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),
                'width':width,'height':height}
    encoding = 'utf-16' if content.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    try:text = content.decode(encoding)
    except UnicodeError:return unavailable('No text preview available for this encoding.')
    if '\0' in text:return unavailable('No preview available for binary files.')
    preview = '\n'.join(text[:65536].split('\n')[:1000])
    return {'kind':'text','text':preview,'truncated':len(preview)<len(text)}


def read(path):
    """Decode in a short-lived worker so a malformed file cannot stall the UI."""
    try:
        result = subprocess.run(['/usr/bin/python3',__file__,path],capture_output=True,text=True,timeout=4,check=True)
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:return unavailable('Preview took too long. Open the file in its app instead.')
    except (subprocess.SubprocessError,ValueError):return unavailable('This file could not be previewed.')


if __name__=='__main__':
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        result=generate(sys.argv[1])
    except PermissionError:result=unavailable('You do not have permission to preview this file.')
    except FileNotFoundError:result=unavailable('This file is no longer available.')
    except Exception:result=unavailable('This file could not be previewed.')
    print(json.dumps(result))
