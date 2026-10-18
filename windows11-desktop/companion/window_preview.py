#!/usr/bin/python3
"""Bounded, disposable XComposite reader: PNG thumbnails or one RGB desktop frame.

Runs separately so closed-window races and X protocol errors cannot crash the
desktop hub. Images stay in memory and are never added to wallpaper/history.
"""
import ctypes as C
import io
import struct
import sys
from PIL import Image


class XImage(C.Structure):
    _fields_=[('width',C.c_int),('height',C.c_int),('xoffset',C.c_int),('format',C.c_int),
              ('data',C.c_void_p),('byte_order',C.c_int),('bitmap_unit',C.c_int),
              ('bitmap_bit_order',C.c_int),('bitmap_pad',C.c_int),('depth',C.c_int),
              ('bytes_per_line',C.c_int),('bits_per_pixel',C.c_int),
              ('red_mask',C.c_ulong),('green_mask',C.c_ulong),('blue_mask',C.c_ulong)]


class Visual(C.Structure):
    _fields_=[('ext_data',C.c_void_p),('visualid',C.c_ulong),('visual_class',C.c_int),
              ('red_mask',C.c_ulong),('green_mask',C.c_ulong),('blue_mask',C.c_ulong),
              ('bits_per_rgb',C.c_int),('map_entries',C.c_int)]


def capture(xid,desktop=False):
    x=C.CDLL('libX11.so.6');comp=C.CDLL('libXcomposite.so.1')
    def signature(lib,name,restype,args):
        fn=getattr(lib,name);fn.restype=restype;fn.argtypes=args;return fn
    display=signature(x,'XOpenDisplay',C.c_void_p,[C.c_char_p])(None)
    if not display:return b''
    error=[False]
    handler=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(lambda *_:(error.__setitem__(0,True),0)[1])
    signature(x,'XSetErrorHandler',C.c_void_p,[C.c_void_p])(handler)
    sync=signature(x,'XSync',C.c_int,[C.c_void_p,C.c_int])
    # Reparenting WMs composite their frame, not the application's child XID.
    query=signature(x,'XQueryTree',C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)])
    free=signature(x,'XFree',C.c_int,[C.c_void_p])
    candidates=[xid]
    for _ in range(12):
        root=C.c_ulong();parent=C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
        query(display,xid,C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
        sync(display,0)
        if children:free(children)
        if error[0]:return b''
        if parent.value==root.value or not parent.value:break
        xid=parent.value;candidates.append(xid)
    name_pixmap=signature(comp,'XCompositeNameWindowPixmap',C.c_ulong,[C.c_void_p,C.c_ulong])
    for candidate in candidates:
        error[0]=False;pix=name_pixmap(display,candidate);sync(display,0)
        if not error[0]:break
    if error[0]:return b''
    root=C.c_ulong();px=C.c_int();py=C.c_int();width=C.c_uint();height=C.c_uint();border=C.c_uint();depth=C.c_uint()
    signature(x,'XGetGeometry',C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),*[C.POINTER(C.c_uint)]*4])(display,pix,C.byref(root),C.byref(px),C.byref(py),C.byref(width),C.byref(height),C.byref(border),C.byref(depth))
    sync(display,0)
    if error[0] or not 1<=width.value*height.value<=18000000:return b''
    ptr=signature(x,'XGetImage',C.POINTER(XImage),[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_ulong,C.c_int])(display,pix,0,0,width.value,height.value,C.c_ulong(-1),2)
    sync(display,0)
    if error[0] or not ptr:return b''
    img=ptr.contents
    # A named pixmap has no associated visual, so XGetImage may return zero
    # channel masks. In that case validate the default TrueColor visual.
    visual=signature(x,'XDefaultVisual',C.POINTER(Visual),[C.c_void_p,C.c_int])(display,0).contents
    masks=(img.red_mask,img.green_mask,img.blue_mask)
    if masks==(0,0,0):masks=(visual.red_mask,visual.green_mask,visual.blue_mask)
    if img.bits_per_pixel!=32 or img.byte_order!=0 or masks!=(0xff0000,0xff00,0xff):return b''
    raw=C.string_at(img.data,img.bytes_per_line*img.height)
    image=Image.frombytes('RGB',(img.width,img.height),raw,'raw','BGRX',img.bytes_per_line)
    if desktop:
        # A single bounded RGB frame avoids PNG encoding/decoding latency in
        # the desktop crossfade. It is sent through the private process pipe.
        data=b'Z11D'+struct.pack('!II',image.width,image.height)+image.tobytes()
    else:
        image.thumbnail((480,280),Image.Resampling.LANCZOS)
        out=io.BytesIO();image.save(out,format='PNG');data=out.getvalue()
    signature(x,'XDestroyImage',C.c_int,[C.POINTER(XImage)])(ptr)
    signature(x,'XFreePixmap',C.c_int,[C.c_void_p,C.c_ulong])(display,pix)
    signature(x,'XCloseDisplay',C.c_int,[C.c_void_p])(display)
    return data


if __name__=='__main__':
    try:sys.stdout.buffer.write(capture(int(sys.argv[1]),'--desktop' in sys.argv))
    except Exception:pass
