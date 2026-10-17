#!/usr/bin/python3
"""Build original caption artwork; only maintainers need GTK's SVG loader."""
from pathlib import Path
import xml.etree.ElementTree as ET
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

ROOT = Path(__file__).resolve().parent/'window-theme'
PATHS = {
    'close': 'M3 3 13 13M13 3 3 13',
    'minimize': 'M3 8.5H13',
    'maximize': 'M3.5 3.5H12.5V12.5H3.5Z',
    'restore': 'M5.5 5.5V2.5H13.5V10.5H10.5M2.5 5.5H10.5V13.5H2.5Z',
    'menu': 'M3 4H13M3 8H13M3 12H13',
    'shade': 'M3 10 8 5 13 10',
    'unshade': 'M3 5 8 10 13 5',
    'stick': 'M5 3H11L10 8 13 11H3L6 8ZM8 11V15',
}


def svg(width, height, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">{body}</svg>'


def png(name, width, height, body):
    loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
    loader.write(svg(width, height, body).encode()); loader.close()
    loader.get_pixbuf().savev(str(ROOT/'xfwm4'/f'{name}.png'), 'png', [], [])


def build():
    for folder in ('controls', 'xfwm4', 'metacity-1'):
        (ROOT/folder).mkdir(parents=True, exist_ok=True)
    for name, path in PATHS.items():
        (ROOT/'controls'/f'{name}.svg').write_text(svg(16,16,f'<path d="{path}" fill="none" stroke="#f5f5f5" stroke-width="1"/>')+'\n')
    # Xfwm uses these pre-rendered strips; there are no runtime image tools.
    for state in ('active','inactive','prelight','pressed'):
        color = '#999999' if state=='inactive' else '#f5f5f5'
        for name, glyph in {'close':'close','hide':'minimize','maximize':'maximize','maximize-toggled':'restore','menu':'menu','shade':'shade','shade-toggled':'unshade','stick':'stick','stick-toggled':'stick'}.items():
            bg = '#c42b1c' if name=='close' and state=='prelight' else '#a92518' if name=='close' and state=='pressed' else '#383838' if state=='prelight' else '#303030' if state=='pressed' else '#202020'
            width = 28 if name=='menu' else 46
            png(f'{name}-{state}',width,32,f'<rect width="{width}" height="32" fill="{bg}"/><path d="{PATHS[glyph]}" transform="translate({(width-16)/2},8)" fill="none" stroke="{color}"/>')
    for state in ('active','inactive'):
        edge = '#4d4d4d' if state=='active' else '#333333'
        for i in range(1,6):
            png(f'title-{i}-{state}',1,32,f'<path d="M.5 0V32" stroke="#202020"/>')
        for side in ('left','right'):
            png(f'{side}-side-{state}',1,1,f'<path d="M.5 0V1" stroke="{edge}"/>')
            png(f'top-{side}-{state}',5,32,f'<rect width="5" height="32" fill="#202020"/><path d="M{0.5 if side=="left" else 4.5} 0V32" stroke="{edge}"/>')
            png(f'bottom-{side}-{state}',5,1,f'<rect width="5" height="1" fill="{edge}"/>')
        png(f'bottom-{state}',1,1,f'<path d="M.5 0V1" stroke="{edge}"/>')
    (ROOT/'xfwm4/themerc').write_text('''active_text_color=#f5f5f5
inactive_text_color=#999999
title_shadow_active=false
title_shadow_inactive=false
button_offset=0
button_spacing=0
full_width_title=true
maximized_offset=0
show_app_icon=true
title_vertical_offset_active=0
title_vertical_offset_inactive=0
title_horizontal_offset=8
shadow_delta_height=4
shadow_delta_width=0
shadow_delta_x=0
shadow_delta_y=-2
shadow_opacity=35
''')
    # Metacity's vector format is used by Compiz's GTK window decorator.
    root = ET.Element('metacity_theme')
    info = ET.SubElement(root,'info')
    for name,value in {'name':'Zorin11-Dark','author':'Zorin Windows 11 desktop project','copyright':'2026 Zorin Windows 11 desktop project','date':'2026-10-17','description':'Original flat dark window captions with Windows-style controls.'}.items():
        ET.SubElement(info,name).text=value
    def el(container, tag, **attrs):return ET.SubElement(container,tag,{k:str(v) for k,v in attrs.items()})
    geom = el(root,'frame_geometry',name='normal',rounded_top_left='true',rounded_top_right='true')
    for name,value in {'left_width':1,'right_width':1,'bottom_height':1,'left_titlebar_edge':1,'right_titlebar_edge':1,'button_width':46,'button_height':32,'title_vertical_pad':4}.items():el(geom,'distance',name=name,value=value)
    el(geom,'border',name='title_border',left=10,right=10,top=0,bottom=0)
    el(geom,'border',name='button_border',left=0,right=0,top=0,bottom=0)
    geom = el(root,'frame_geometry',name='maximized',parent='normal',rounded_top_left='false',rounded_top_right='false')
    for name in ('left_width','right_width','bottom_height','left_titlebar_edge','right_titlebar_edge'):el(geom,'distance',name=name,value=0)
    for focus,color,edge in [('active','#f5f5f5','#4d4d4d'),('inactive','#999999','#333333')]:
        ops=el(root,'draw_ops',name=f'frame_{focus}')
        el(ops,'rectangle',color='#202020',x=0,y=0,width='width',height='height',filled='true')
        el(ops,'rectangle',color=edge,x=0,y=0,width='width-1',height='height-1',filled='false')
        ops=el(root,'draw_ops',name=f'title_{focus}')
        el(ops,'icon',x=0,y='(height-16)/2',width=16,height=16)
        el(ops,'title',color=color,x=24,y='(height-title_height)/2')
        for glyph in ('close','minimize','maximize','restore','menu'):
            for state in ('normal','prelight','pressed'):
                ops=el(root,'draw_ops',name=f'{glyph}_{focus}_{state}')
                if state!='normal':
                    bg='#c42b1c' if glyph=='close' and state=='prelight' else '#a92518' if glyph=='close' else '#383838' if state=='prelight' else '#303030'
                    el(ops,'rectangle',color=bg,x=0,y=0,width='width',height='height',filled='true')
                if glyph=='menu':el(ops,'icon',x='(width-16)/2',y='(height-16)/2',width=16,height=16)
                else:el(ops,'image',filename=f'../controls/{glyph}.svg',x='(width-16)/2',y='(height-16)/2',width=16,height=16,alpha='0.55' if focus=='inactive' and state=='normal' else '1')
        for mode in ('normal','maximized'):
            style=el(root,'frame_style',name=f'{focus}_{mode}',geometry=mode)
            el(style,'piece',position='entire_background',draw_ops=f'frame_{focus}')
            el(style,'piece',position='title',draw_ops=f'title_{focus}')
            for button in ('close','minimize','maximize','menu'):
                glyph='restore' if mode=='maximized' and button=='maximize' else button
                for state in ('normal','prelight','pressed'):el(style,'button',function=button,state=state,draw_ops=f'{glyph}_{focus}_{state}')
    styles=el(root,'frame_style_set',name='windows')
    for focus in ('yes','no'):
        prefix='active' if focus=='yes' else 'inactive'
        for state in ('normal','shaded','maximized','maximized_and_shaded'):
            attrs={'focus':focus,'state':state,'style':f'{prefix}_{"maximized" if state.startswith("maximized") else "normal"}'}
            if state=='normal':attrs['resize']='both'
            el(styles,'frame',**attrs)
    for kind in ('normal','dialog','modal_dialog','menu','utility','border'):el(root,'window',type=kind,style_set='windows')
    for button in ('close','minimize','maximize','unmaximize'):el(root,'menu_icon',function=button,state='normal',draw_ops=f'{"restore" if button=="unmaximize" else button}_active_normal')
    ET.indent(root)
    ET.ElementTree(root).write(ROOT/'metacity-1/metacity-theme-1.xml',encoding='utf-8',xml_declaration=True)


if __name__=='__main__':build()
