"""Narrow upgrade for existing minified Explorer bundles; preserve local integrations."""
import re
from pathlib import Path


def patch_bundle(text):
    if 'Click to edit or copy the folder path (Ctrl+L)' in text:
        return text
    match = re.search(r'className:"address",onDoubleClick:\(\)=>('+r'[$\w]+'+r')\(('+r'[$\w]+'+r')\.path\.startsWith\("::"\)\?"":\2\.path\)', text)
    if not match:
        raise RuntimeError('Unknown Explorer address structure; refusing to replace the frontend.')
    setter, data = match.groups()
    edit = f'{setter}({data}.path.startsWith("::")?"":{data}.path)'
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError('Ambiguous Explorer address structure; no files written.')
        text = text.replace(old, new)
    replace(match.group(), f'className:"address",title:"Click to edit or copy the folder path (Ctrl+L)",onClick:ev=>{{if(!ev.target.closest("button,input")){edit}}},onDoubleClick:()=>{edit}')
    # Find the containing Explorer key handler's input guard, not other surfaces.
    address_at = text.index('className:"address"')
    shell_at = text.rfind('className:"explorer-shell"', 0, address_at)
    if shell_at < 0:
        shell_at = text.rfind('className:"explorer-shell"+', 0, address_at)
    prefix = text[shell_at:address_at]
    guard = re.search(r'if\(([$\w]+)\.target\.matches\("input"\)\)return;', prefix)
    if shell_at < 0 or not guard:
        raise RuntimeError('Unknown Explorer keyboard structure.')
    ev = guard.group(1)
    old = guard.group()
    extra = f'if(({ev}.ctrlKey&&{ev}.key.toLowerCase()==="l")||({ev}.altKey&&{ev}.key.toLowerCase()==="d")||{ev}.key==="F4"){{{ev}.preventDefault();{edit};requestAnimationFrame(()=>{{let el=document.querySelector(".explorer-shell .address input");el?.focus();el?.select()}});return}}'
    offset = shell_at + guard.start()
    text = text[:offset] + extra + text[offset:]
    # Last breadcrumb edits; ancestor buttons retain navigation.
    block = re.search(r'([$\w]+)\.map\(\(([$\w]+),([$\w]+)\)=>.{0,400}?onClick:\(\)=>\s*([$\w]+)\(\2\.path\)', text[address_at:])
    if not block:
        raise RuntimeError('Unknown breadcrumb structure.')
    crumbs, crumb, index, navigate = block.groups()
    old = f'onClick:()=>{navigate}({crumb}.path)'
    pos = address_at + block.end() - len(old)
    if text[pos:pos+len(old)] != old:
        raise RuntimeError('Breadcrumb anchor mismatch.')
    new = f'title:{index}==={crumbs}.length-1?"Edit or copy folder path":{crumb}.path,onClick:()=>{index}==={crumbs}.length-1?{edit}:{navigate}({crumb}.path)'
    text = text[:pos] + new + text[pos+len(old):]
    handler = re.search(r'onKeyDown:([$\w]+)=>\{\1\.key==="Enter"&&([$\w]+)\(([$\w]+)\),\1\.key==="Escape"&&'+re.escape(setter)+r'\(null\)\}', text[address_at:])
    if not handler:
        raise RuntimeError('Unknown address input handler.')
    ev, nav, value = handler.groups()
    old = handler.group()
    new = f'onKeyDown:{ev}=>{{if({ev}.key==="Enter"){{{ev}.preventDefault();{ev}.stopPropagation();if({value}.trim()){nav}({value})}}if({ev}.key==="Escape"){{{ev}.preventDefault();{ev}.stopPropagation();{setter}(null);document.querySelector(".explorer-shell")?.focus()}}}}'
    replace(old, new)
    return text


def install():
    import gnome_install
    path = Path.home()/'.local/share/zorin11-hub/dist/main.js'
    original = path.read_text()
    changed = patch_bundle(original)
    gnome_install.write_files({path: changed.encode()})
    print('Explorer address behavior updated; all other bundle content preserved.')

if __name__ == '__main__': install()
