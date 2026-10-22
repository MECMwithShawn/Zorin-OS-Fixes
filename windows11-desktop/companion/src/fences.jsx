import React,{useEffect,useRef,useState} from 'react';
import './fences.css';
const send=(action,payload={})=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));
const key=item=>item.id;
const fileUri=path=>'file://'+path.split('/').map(encodeURIComponent).join('/');
// A new fence asks to be named before its component has mounted; remember it.
let renameRequested=false;
window.addEventListener('desktop-message',e=>{if(e.detail.type==='rename-fence'){renameRequested=true;window.dispatchEvent(new Event('fence-rename'));}});
const ICON={small:[68,32],medium:[86,44],large:[108,60]};
function rgb(hex){const v=parseInt(hex.slice(1),16);return[(v>>16)&255,(v>>8)&255,v&255];}
const Chevron=({up})=><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d={up?'M3.5 10l4.5-4.5 4.5 4.5':'M3.5 6l4.5 4.5 4.5-4.5'} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const More=()=><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="3.5" cy="8" r="1.3" fill="currentColor"/><circle cx="8" cy="8" r="1.3" fill="currentColor"/><circle cx="12.5" cy="8" r="1.3" fill="currentColor"/></svg>;

export function Fence({data,toast}){
 const g=data.group,style={tint:'slate',opacity:.55,iconSize:'medium',sort:'manual',autoRoll:false,...g.style},tints=g.tints||{slate:'#20242a'};
 const [selected,setSelected]=useState(null),[hover,setHover]=useState(false),[dropping,setDropping]=useState(false);
 const [renaming,setRenaming]=useState(false),[title,setTitle]=useState(g.title);
 const dragging=useRef(null),handled=useRef(false),root=useRef(null);
 useEffect(()=>{const start=()=>{if(!renameRequested)return;renameRequested=false;setTitle(g.title);setRenaming(true);};
  start();window.addEventListener('fence-rename',start);return()=>window.removeEventListener('fence-rename',start);},[g.title]);
 useEffect(()=>{if(!g.items.some(i=>key(i)===selected))setSelected(null);},[g.items,selected]);
 const [r,gr,b]=rgb(tints[style.tint]||'#20242a'),light=(r*299+gr*587+b*114)/1000>150;
 const [tile,icon]=ICON[style.iconSize]||ICON.medium;
 const open=item=>send(item.kind==='path'?'open-path':'launch',item.kind==='path'?{path:item.path}:{id:item.id});
 const showContent=!g.collapsed||(style.autoRoll&&hover);
 const commit=()=>{setRenaming(false);const next=title.trim();if(next&&next!==g.title)send('rename-group',{group:g.id,title:next});};
 const hovering=inside=>{setHover(inside);if(g.collapsed&&style.autoRoll)send('fence-hover',{inside});};
 const internal=e=>[...e.dataTransfer.types].includes('application/x-zorin11-fence');
 return <main ref={root} className={'fence'+(light?' light':'')+(g.collapsed?' rolled':'')+(dropping?' dropping':'')+(data.peeking?' peeking':'')}
  style={{'--fence-bg':`rgba(${r},${gr},${b},${style.opacity})`,'--tile':tile+'px','--icon':icon+'px'}}
  onMouseEnter={()=>hovering(true)} onMouseLeave={()=>hovering(false)}
  onContextMenu={e=>{e.preventDefault();if(!e.target.closest('.fence-item'))send('fence-menu');}}
  onKeyDown={e=>{if(e.key==='F10'&&e.shiftKey||e.key==='ContextMenu'){e.preventDefault();send('fence-menu',{id:selected,keyboard:true});}}}
  onDragOver={e=>{e.preventDefault();if(!internal(e)||dragging.current===null)setDropping(true);}}
  onDragLeave={e=>{if(!e.relatedTarget||!root.current.contains(e.relatedTarget))setDropping(false);}}
  onDrop={e=>{e.preventDefault();setDropping(false);handled.current=true;}}>
  <header className="fence-titlebar" onMouseDown={e=>{if(e.button===0&&!e.target.closest('button,input'))send('move');}}
   onDoubleClick={e=>{if(!e.target.closest('button,input'))send('collapse',{group:g.id});}}>
   {renaming?<input className="fence-rename" aria-label="Fence name" value={title} autoFocus maxLength={60}
     onChange={e=>setTitle(e.target.value)} onBlur={commit} onFocus={e=>e.target.select()}
     onKeyDown={e=>{e.stopPropagation();if(e.key==='Enter')commit();if(e.key==='Escape'){setRenaming(false);setTitle(g.title);}}}/>
    :<strong title={g.title}>{g.title}</strong>}
   {g.collapsed&&<span className="fence-count">{g.items.length}</span>}
   <span className="fence-actions">
    <button aria-label="Fence options" title="Fence options" onClick={()=>send('fence-menu')}><More/></button>
    <button aria-label={g.collapsed?'Unroll fence':'Roll up fence'} title={g.collapsed?'Unroll':'Roll up'} onClick={()=>send('collapse',{group:g.id})}><Chevron up={!g.collapsed}/></button>
   </span>
  </header>
  {showContent&&<><div className="fence-body" onClick={e=>{if(e.target===e.currentTarget)setSelected(null);}}>
   {g.error&&<p className="fence-note">This folder is unavailable. Choose another folder in Manage fences.</p>}
   <div className="fence-grid" role="listbox" aria-label={g.title}>{g.items.map(item=>{
    const id=key(item),canDrag=item.kind==='path';
    return <button key={id} role="option" aria-selected={selected===id} className={'fence-item'+(selected===id?' selected':'')+(item.missing?' missing':'')}
     title={item.missing?item.name+' (missing)':item.name} draggable={!g.folder||canDrag}
     onClick={()=>setSelected(id)} onFocus={()=>setSelected(id)} onDoubleClick={()=>open(item)}
     onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();open(item);}else if(e.key==='Delete'&&!g.folder)send('remove-item',{group:g.id,id});}}
     onContextMenu={e=>{e.preventDefault();e.stopPropagation();setSelected(id);send('fence-menu',{id});}}
     onDragStart={e=>{dragging.current=id;handled.current=false;e.dataTransfer.effectAllowed='copyMove';
      e.dataTransfer.setData('application/x-zorin11-fence',id);if(canDrag){e.dataTransfer.setData('text/uri-list',fileUri(item.path));e.dataTransfer.setData('text/plain',fileUri(item.path));}}}
     onDragOver={e=>{if(internal(e)&&dragging.current!==null&&!g.folder&&style.sort==='manual'){e.preventDefault();e.currentTarget.classList.add('drop-before');}}}
     onDragLeave={e=>e.currentTarget.classList.remove('drop-before')}
     onDrop={e=>{e.currentTarget.classList.remove('drop-before');if(dragging.current!==null&&dragging.current!==id&&!g.folder){e.preventDefault();e.stopPropagation();handled.current=true;setDropping(false);send('fence-reorder',{id:dragging.current,target:id});}}}
     onDragEnd={e=>{const out=e.clientX<0||e.clientY<0||e.clientX>innerWidth||e.clientY>innerHeight;
      if(!handled.current&&canDrag&&!g.folder&&(out||e.dataTransfer.dropEffect!=='none'))send('fence-dropped-out',{path:item.path});
      dragging.current=null;setDropping(false);}}>
     <img src={item.icon} alt="" draggable="false" onError={e=>{e.currentTarget.src='zorin11://icon/file';}}/>
     <span>{item.name}</span>
    </button>;})}</div>
   {!g.items.length&&!g.error&&<div className="fence-empty"><strong>Drag icons here</strong><span>{g.folder?'This fence mirrors a folder.':'Files stay on your desktop; the fence just keeps them tidy.'}</span></div>}
   {g.overflow&&<p className="fence-note">Showing the first 200 items. Open the folder to see everything.</p>}
  </div>
  {!g.collapsed&&<button className="fence-resize" aria-label="Resize fence" title="Drag to resize" onMouseDown={e=>{if(e.button===0){e.preventDefault();send('resize');}}}/>}</>}
  {dropping&&<div className="fence-drop-hint" aria-hidden="true">Drop to add to {g.title}</div>}
  {data.peeking&&<div className="fence-peek" role="status">Peek · Esc to send back</div>}
  {toast&&<div role="alert" className="fence-toast">{toast}</div>}
 </main>;
}
