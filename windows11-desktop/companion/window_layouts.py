"""Monitor-relative geometry for explicitly saved whole-desktop layouts."""
import gi
gi.require_version('Gdk','3.0')
from gi.repository import Gdk


def monitors():
    display=Gdk.Display.get_default();primary=display.get_primary_monitor();rows=[]
    for i in range(display.get_n_monitors()):
        m=display.get_monitor(i);a=m.get_workarea()
        rows.append(dict(index=i,model=m.get_model() or '',manufacturer=m.get_manufacturer() or '',
                         primary=m==primary,area=[a.x,a.y,a.width,a.height]))
    return rows


def encode(rect,outputs):
    def overlap(m):
        x,y,w,h=m['area'];a,b,c,d=rect
        return max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
    monitor=max(outputs,key=overlap);x,y,w,h=monitor['area'];a,b,c,d=rect
    return dict(monitor=monitor,rect=[(a-x)/w,(b-y)/h,c/w,d/h])


def decode(member,outputs):
    saved=member['monitor']
    matching=[m for m in outputs if m['model'] and (m['model'],m['manufacturer'])==(saved['model'],saved['manufacturer'])]
    monitor=next((m for m in matching if m['index']==saved['index']),matching[0] if matching else None)
    missing=monitor is None
    if missing:monitor=next((m for m in outputs if m['primary']),outputs[0])
    x,y,w,h=monitor['area'];a,b,c,d=member['rect']
    width=max(1,round(c*w));height=max(1,round(d*h));left=x+round(a*w);top=y+round(b*h)
    if missing:
        width=min(width,w);height=min(height,h)
        left=max(x,min(left,x+w-width));top=max(y,min(top,y+h-height))
    else:
        # Keep a usable title-bar portion reachable, including spanning windows.
        left=max(x-width+80,min(left,x+w-80));top=max(y,min(top,y+h-40))
    return left,top,width,height
