import React from 'react';
const edges=['north','south','west','east','north-west','north-east','south-west','south-east'];
const send=(action,payload={})=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));
export function MaximizeButton({maximized,onMaximize,children}){
 const cancel=()=>send('snap-hover',{enter:false});
 const layouts=e=>{e.preventDefault();e.stopPropagation();cancel();send('snap-layouts');};
 const name=maximized?'Restore down':'Maximize';
 return <button aria-label={name} title={name+' · Right-click or press ↓ for Snap layouts'}
  onMouseEnter={()=>send('snap-hover',{enter:true})} onMouseLeave={cancel}
  onContextMenu={layouts} onKeyDown={e=>{if(e.key==='ArrowDown'||e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))layouts(e);}}
  onClick={()=>{cancel();onMaximize();}}>{children}</button>;
}
export function WindowEdges(){
 return <div className="window-edges" aria-hidden="true">{edges.map(edge=><div key={edge} className={'window-edge '+edge} onMouseDown={e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action:'window-resize',edge}));}}/>)}</div>;
}
