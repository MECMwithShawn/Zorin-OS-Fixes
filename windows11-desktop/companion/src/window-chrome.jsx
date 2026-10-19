import React from 'react';
const edges=['north','south','west','east','north-west','north-east','south-west','south-east'];
export function WindowEdges(){
 return <div className="window-edges" aria-hidden="true">{edges.map(edge=><div key={edge} className={'window-edge '+edge} onMouseDown={e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action:'window-resize',edge}));}}/>)}</div>;
}
