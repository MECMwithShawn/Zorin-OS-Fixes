import React,{useEffect,useRef,useState} from 'react';
import {Glyph} from './explorer.jsx';
import {FilePreview} from './file-preview.jsx';
import './unified-search.css';
const send=(action,payload={})=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));
let sequence=0;
const filters=[['all','All'],['app','Apps'],['file','Files'],['folder','Folders'],['setting','Settings']];
const labels={app:'App',file:'File',folder:'Folder',setting:'Settings'};
const detailRows=[['version','Version'],['publisher','Publisher'],['source','Installed from'],['package','Package'],['size','Size on disk']];
function Icon({item}){return item.kind==='app'?<img src={item.icon} alt=""/>:<Glyph name={item.kind==='setting'?'settings':item.kind==='folder'?'folder':'document'} size={24}/>;}

export function UnifiedSearch({query,input}){
 const [response,setResponse]=useState(null),[filter,setFilter]=useState('app'),[selected,setSelected]=useState(null);
 const root=useRef(null);
 useEffect(()=>{
  const id=++sequence;setResponse(null);setSelected(null);
  const receive=e=>{if(e.detail.type==='search-results'&&e.detail.id===id)setResponse({...e.detail,query});};
  window.addEventListener('desktop-message',receive);
  const timer=setTimeout(()=>send('search-query',{id,query}),180);
  return()=>{clearTimeout(timer);window.removeEventListener('desktop-message',receive);send('search-cancel');};
 },[query]);
 const items=(response?.results||[]).filter(i=>filter==='all'||filter===i.kind);
 const index=Math.max(0,items.findIndex(i=>i.key===selected)),item=items[index];
 const open=(result,location=false)=>result&&send(location?'search-location':'search-open',{key:result.key});
 const [details,setDetails]=useState(null);
 useEffect(()=>{
  setDetails(null);if(item?.kind!=='app')return;
  const key=item.key,receive=e=>{if(e.detail.type==='app-details'&&e.detail.key===key)setDetails(e.detail);};
  window.addEventListener('desktop-message',receive);send('search-app-details',{key});
  return()=>window.removeEventListener('desktop-message',receive);
 },[item?.key]);
 useEffect(()=>{
  const keys=e=>{
   if(!['ArrowDown','ArrowUp','Enter'].includes(e.key)||!items.length)return;
   if(document.activeElement!==input.current&&!document.activeElement?.matches('.unified-result'))return;
   e.preventDefault();e.stopPropagation();
   if(e.key==='Enter'){open(item);return;}
   const next=Math.max(0,Math.min(items.length-1,index+(e.key==='ArrowDown'?1:-1)));setSelected(items[next].key);
   root.current?.querySelectorAll('.unified-result')[next]?.scrollIntoView({block:'nearest'});
   if(document.activeElement!==input.current)root.current?.querySelectorAll('.unified-result')[next]?.focus();
  };
  document.addEventListener('keydown',keys,true);return()=>document.removeEventListener('keydown',keys,true);
 },[items,index,item]);
 return <section ref={root} className="unified-search" data-query={response?.query} data-searching={!response||!!response.searching} aria-label="Search results">
  <nav className="search-filters" aria-label="Search categories">{filters.map(([id,label])=><button key={id} aria-pressed={filter===id} onClick={()=>{setFilter(id);setSelected(null);}}>{label}</button>)}</nav>
  <div className="unified-status" role="status">{!response||response.searching?'Searching…':response.error?'Search unavailable: '+response.error:items.length?`${items.length} ${items.length===1?'result':'results'} · ${filter==='app'?'Click or press Enter to open':'Enter or double-click to open'}`:'No matching results.'}</div>
  <div className="unified-layout"><div className="unified-results" aria-label="Matching items">{items.map((result,i)=><button key={result.key} className={'unified-result'+(i===index?' selected':'')} aria-label={result.name+', '+labels[result.kind]} aria-current={i===index?'true':undefined} onFocus={()=>setSelected(result.key)} onMouseEnter={()=>result.kind==='app'&&setSelected(result.key)} onClick={()=>result.kind==='app'?open(result):setSelected(result.key)} onDoubleClick={()=>result.kind!=='app'&&open(result)}>
   <Icon item={result}/><span><strong>{result.name}</strong><small>{labels[result.kind]}{['file','folder'].includes(result.kind)?' · '+result.description:''}</small></span>
  </button>)}</div>
  {item&&<section className="search-detail" aria-label="Selected result"><div className="search-detail-heading">{item.kind==='app'?<button className="search-launch" aria-label={'Open '+item.name} title={'Open '+item.name} onClick={()=>open(item)}><Icon item={item}/></button>:<Icon item={item}/>}<h2>{item.name}</h2><p>{item.description||labels[item.kind]}</p></div>
  {item.kind==='app'?<dl className="search-app-details" aria-busy={details?.key!==item.key}>{details?.key===item.key?detailRows.filter(([id])=>details.details?.[id]).map(([id,label])=><div key={id}><dt>{label}</dt><dd>{details.details[id]}</dd></div>):<div><dt>Details</dt><dd>Loading…</dd></div>}{(item.categories||[]).filter(Boolean).length>0&&<div><dt>Category</dt><dd>{item.categories.filter(Boolean).join(', ')}</dd></div>}</dl>
  :<div className="search-result-actions"><button onClick={()=>open(item)}>Open</button>{item.path&&<button onClick={()=>open(item,true)}>Open file location</button>}</div>}
  {item.kind==='app'&&<div className="search-app-actions">{(item.actions||[]).map(action=><button key={action.id} onClick={()=>send('app-action',{id:item.id,shortcut:action.id})}>{action.name}</button>)}</div>}
  {item.kind==='file'&&<FilePreview item={item} location={query} actionPrefix="search"/>}
  </section>}</div>
  <p className="search-scope">Files: {response?.scope?.length??0} search folders. Hidden items, links and excluded folders stay private. <button onClick={()=>send('settings',{page:'search-start'})}>Choose folders</button>{response?.filesNeedMore?' Type at least two characters to search files.':''}{response?.limited?' Search was limited; some files may be missing.':''}</p>
 </section>;
}
