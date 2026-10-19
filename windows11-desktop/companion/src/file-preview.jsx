import React,{useEffect,useState} from 'react';
const send=(action,payload={})=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));
let previewSequence=0;

export function FilePreview({item,location,onClose,actionPrefix="file"}){
 const [result,setResult]=useState(null);
 useEffect(()=>{
  const id=++previewSequence;setResult(null);
  const receive=e=>{if(e.detail.type==='file-preview'&&e.detail.id===id)setResult(e.detail.result);};
  window.addEventListener('desktop-message',receive);
  const timer=item&&!item.folder?setTimeout(()=>send(actionPrefix+'-preview',{path:item.path,key:item.key,id}),120):null;
  return()=>{clearTimeout(timer);window.removeEventListener('desktop-message',receive);send(actionPrefix+'-preview-cancel');};
 },[item?.path,item?.modified,item?.size,location,actionPrefix]);
 return <aside className="explorer-preview" aria-label="Preview pane">
  <header><h2>Preview</h2>{onClose&&<button aria-label="Close preview pane" onClick={onClose}>×</button>}</header>
  {item&&<h3>{item.name}</h3>}
  <div className="preview-content" role="region" aria-label="File preview" aria-busy={!!item&&!item.folder&&!result}>
   {!item?<p>Select one file to preview.</p>:item.folder?<p>Select a file to preview its contents.</p>:!result?<p role="status">Loading preview…</p>:
    result.kind==='image'?<><img src={result.image} alt={'Preview of '+item.name}/><p>{result.width} × {result.height}</p></>:
    result.kind==='text'?<><pre tabIndex={0}>{result.text||'Empty file'}</pre>{result.truncated&&<p>Showing the beginning of this file.</p>}</>:
    <p role="status">{result.message}</p>}
  </div>
 </aside>;
}
