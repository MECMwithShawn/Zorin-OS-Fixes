import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {Explorer} from './explorer.jsx';
import {UnifiedSearch} from './unified-search.jsx';
import './explorer.css';
import {Settings} from './settings.jsx';
import {QuickSettings,NotificationCenter} from './flyouts.jsx';
import './window-chrome.css';
import './start-classic.css';
import './start-windows10.css';
import './start-modern.css';
import './start-more.css';

window.desktopErrors = [];
window.addEventListener('error', e => window.desktopErrors.push(e.message));
const send = (action, payload={}) => window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));

function Symbol({name,size=20}) {
 const paths={search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
  arrow:<path d="m9 5 7 7-7 7"/>,back:<path d="m15 5-7 7 7 7"/>,down:<path d="m6 9 6 6 6-6"/>,
  plus:<path d="M12 5v14M5 12h14"/>,close:<path d="m6 6 12 12M18 6 6 18"/>,
  power:<><path d="M12 3v9M6 5a9 9 0 1 0 12 0"/></>,
  restart:<><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/></>,
  sleep:<path d="M20 15A8.5 8.5 0 0 1 9 4a8.5 8.5 0 1 0 11 11Z"/>,
  logout:<><path d="M10 4H4v16h6M9 12h12m-4-4 4 4-4 4"/></>,
  switchUser:<><circle cx="8" cy="7" r="3"/><path d="M2 19v-2a6 6 0 0 1 12 0M16 6h6m-2-2 2 2-2 2M22 13h-6m2-2-2 2 2 2"/></>,
  user:<><circle cx="12" cy="8" r="4"/><path d="M4 22v-2a8 8 0 0 1 16 0v2"/></>,
  grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  folder:<path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3Z"/>,
  settings:<><path d="m9 3-1 3-3 1-2 4 2 3v4l4 2 3-1 3 1 4-2v-4l2-3-2-4-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/></>,
  pin:<path d="m8 3 8 0-1 6 4 4H5l4-4ZM12 13v8"/>,
  lock:<><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
  eye:<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12"/><circle cx="12" cy="12" r="3"/></>,
  more:<><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  resize:<path d="m9 21 12-12M15 21l6-6"/>,
  menu:<path d="M4 6h16M4 12h16M4 18h16"/>};
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.grid}</svg>;
}

function SessionMenu({kind,trigger,onClose,onAction}) {
 const menu=useRef(null);
 useEffect(()=>{menu.current?.querySelector('button')?.focus();},[kind]);
 const items=kind==='account'
  ?[['user','Account settings','accounts'],['lock','Lock','lock'],['switchUser','Switch user','switch-user'],['logout','Sign out','sign-out']]
  :kind==='classic'
  ?[['switchUser','Switch user','switch-user'],['logout','Sign out','sign-out'],['lock','Lock','lock'],['restart','Restart','restart'],['sleep','Sleep','sleep']]
  :[['sleep','Sleep','sleep'],['power','Shut down','shutdown'],['restart','Restart','restart']];
 return <div ref={menu} className={'power-menu session-menu '+kind+'-menu'} role="menu" aria-label={kind==='account'?'Account menu':kind==='classic'?'Shut down options':'Power menu'} onClick={e=>e.stopPropagation()} onKeyDown={e=>{
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onClose();trigger.current?.focus();}
  if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const buttons=[...menu.current.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowUp'?-1:1)+buttons.length)%buttons.length]?.focus();}
 }}>
 {items.map(([icon,label,action])=><button role="menuitem" key={action} onClick={()=>onAction(action)}><Symbol name={icon} size={18}/>{label}</button>)}
 </div>;
}

function App(){
 useEffect(()=>{
  const media=window.matchMedia('(prefers-reduced-motion:reduce)');
  // Restyle immediately when GTK/WebKit updates the live preference.
  const apply=()=>document.documentElement.toggleAttribute('data-reduced-motion',media.matches);
  apply();media.addEventListener('change',apply);
  return()=>media.removeEventListener('change',apply);
 },[]);
 const [data,setData]=useState(null),[page,setPage]=useState('home'),[query,setQuery]=useState('');
 const [category,setCategory]=useState(null),[appView,setAppView]=useState('Category');
 const [context,setContext]=useState(null),[toast,setToast]=useState(''),[footerMenu,setFooterMenu]=useState(null);
 const [addTo,setAddTo]=useState(null),[newName,setNewName]=useState(''),[rename,setRename]=useState(null);
 const [startFolder,setStartFolder]=useState(null),[folderPicker,setFolderPicker]=useState(null),[folderName,setFolderName]=useState('');
 const [openCategory,setOpenCategory]=useState(null),[placeHover,setPlaceHover]=useState(null);
 const [railOpen,setRailOpen]=useState(false),[letterGrid,setLetterGrid]=useState(false);
 const [launcherChip,setLauncherChip]=useState('pinned');
 const [pinTab,setPinTab]=useState('pinned'),[pinPage,setPinPage]=useState(0),[tabName,setTabName]=useState(null);
 const search=useRef(null),drag=useRef(null),root=useRef(null),nameCancelled=useRef(false);
 const accountButton=useRef(null),powerButton=useRef(null);
 useEffect(()=>{
  window.receive=message=>{
   window.dispatchEvent(new CustomEvent('desktop-message',{detail:message}));
   if(message.type==='state'){window.desktopState=message.data;setData(message.data);}
   if(message.type==='show'){setPage(message.page||'home');setQuery('');setContext(null);setAddTo(null);setFooterMenu(null);setCategory(null);setStartFolder(null);setFolderPicker(null);setOpenCategory(null);setRailOpen(false);setLetterGrid(false);setPinPage(0);setTabName(null);setTimeout(()=>search.current?.focus(),40);}
   if(message.type==='escape')window.dispatchEvent(new Event('start-escape'));
   if(message.type==='error'||message.type==='notice'){setToast(message.message);setTimeout(()=>setToast(''),5000);}
  };
  send('ready');
  return ()=>delete window.receive;
 },[]);
 useEffect(()=>{
  const dismiss=()=>{if(context)setContext(null);else if(tabName){nameCancelled.current=true;setTabName(null);}else if(folderPicker)setFolderPicker(null);else if(startFolder)setStartFolder(null);else if(addTo)setAddTo(null);else if(footerMenu)setFooterMenu(null);else if(data?.mode==='start')send('close');};
  const close=e=>{if(e.key==='Escape'){e.preventDefault();dismiss();}};
  document.addEventListener('keydown',close);window.addEventListener('start-escape',dismiss);
  return()=>{document.removeEventListener('keydown',close);window.removeEventListener('start-escape',dismiss);};
 },[context,footerMenu,addTo,startFolder,folderPicker,tabName,data?.mode]);
 useEffect(()=>{if(startFolder||folderPicker)setTimeout(()=>document.querySelector('.start-folder-dialog button,.start-folder-picker button')?.focus(),0);},[startFolder,folderPicker]);
 useEffect(()=>{if(context)setTimeout(()=>document.querySelector('.start-shell>.context-menu button')?.focus(),0);},[context]);
 // Shared appearance: tint transparency and corner shape apply to every Start style.
 useEffect(()=>{
  const look=data?.mode==='start'?data.startAppearance:null,root=document.documentElement;
  if(!look){root.style.removeProperty('--start-tint');delete root.dataset.startCorners;delete root.dataset.startTransparent;return;}
  root.style.setProperty('--start-tint',String(1-look.transparency/100));
  if(look.transparency)root.dataset.startTransparent='';else delete root.dataset.startTransparent;
  if(look.corners==='style')delete root.dataset.startCorners;else root.dataset.startCorners=look.corners;
 },[data?.mode,data?.startAppearance?.transparency,data?.startAppearance?.corners]);
 // A cancelled name may never blur; clear the flag whenever a new edit begins.
 useEffect(()=>{if(tabName)nameCancelled.current=false;},[!!tabName]);
 useEffect(()=>{if(startFolder&&data?.startFolders&&!data.startFolders.some(f=>f.id===startFolder))setStartFolder(null);},[data?.startFolders,startFolder]);
 if(!data)return <div className="loading">Opening your desktop…</div>;
 const apps=data.apps||[];const byId=Object.fromEntries(apps.map(a=>[a.id,a]));
 const folders=data.startFolders||[],folderById=Object.fromEntries(folders.map(f=>[f.id,{...f,kind:'start-folder'}]));
 const pinnedApps=new Set([...(data.pins||[]),...folders.flatMap(f=>f.apps)]);
 const currentFolder=folderById[startFolder];
 // Windows 11 layout options: rows of pins per page and recommendation count per layout.
 const options=data.startOptions||{layout:'default',columns:6,showRecommended:true,tabs:[]};
 const [pinRows,recommendedCount]={'more-pins':[4,2],'more-recommendations':[2,8]}[options.layout]||[3,6];
 const activeTab=options.tabs.find(t=>t.id===pinTab)||null;
 const recommended=[...(data.documents||[]).slice(0,data.recent?.length?Math.ceil(recommendedCount/2):recommendedCount),...(data.recent||[]).map(id=>byId[id]).filter(Boolean)].slice(0,recommendedCount);
 const categoryFor=app=>{const kinds=app.categories||[];return [['Accessibility','Accessibility'],['Graphics','Creativity'],['Development','Developer Tools'],['AudioVideo','Entertainment'],['Game','Games'],['Office','Productivity'],['Network','Internet'],['Education','Education'],['Settings','System Tools'],['System','System Tools'],['Utility','Utilities']].find(([key])=>kinds.includes(key))?.[1]||'Other';};
 const categories=[...new Set(apps.map(categoryFor))].sort().map(name=>({name,apps:apps.filter(a=>categoryFor(a)===name)}));
 const visibleApps=page==='category'?apps.filter(a=>categoryFor(a)===category):page==='recent'?data.recent.map(id=>byId[id]).filter(Boolean):apps;
 const matches=visibleApps.filter(a=>(a.name+' '+a.description).toLowerCase().includes(query.trim().toLowerCase()));
 const pin=(app,value)=>{send('pin',{id:app.id,value});setContext(null);};
 const open=item=>{if(item.kind==='start-folder'){setStartFolder(item.id);setFolderName(item.name);}else send(item.kind==='document'?'recent-open':item.kind==='path'?'open-path':'launch',item.kind==='path'?{path:item.path}:{id:item.id});setContext(null);};
 const menu=(e,item,group,folder)=>{e.preventDefault();e.stopPropagation();const rect=e.currentTarget.getBoundingClientRect();setContext({x:Math.max(6,Math.min(e.clientX||rect.left,innerWidth-242)),y:Math.max(6,Math.min(e.clientY||rect.bottom,innerHeight-260)),item,group,folder});};
 const icon=item=><img className="app-icon" src={item.icon} alt="" draggable="false" onError={e=>{e.currentTarget.src='zorin11://icon/file';}}/>;
 const dropMode=(e,app,folder)=>{const r=e.currentTarget.getBoundingClientRect(),x=(e.clientX-r.left)/r.width;return !folder&&byId[drag.current]&&app.id!==drag.current&&x>.25&&x<.75?'folder':'reorder';};
 const tile=(app,{pinned=false,group=null,folder=null}={})=><button key={app.id} className={'app-tile'+(app.missing?' missing':'')} title={app.name+(app.missing?' — unavailable':'')}
   onClick={()=>open(app)} onContextMenu={e=>menu(e,app,group,folder)} onKeyDown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))menu(e,app,group,folder);}}
   draggable={pinned||!!folder} onDragStart={e=>{drag.current=app.id;e.dataTransfer.setData('text/plain',app.id);e.dataTransfer.effectAllowed='move';}}
   onDragOver={e=>{if(pinned||folder){e.preventDefault();e.currentTarget.classList.toggle('folder-drop',dropMode(e,app,folder)==='folder');e.currentTarget.classList.add('drag-over');}}}
   onDragLeave={e=>e.currentTarget.classList.remove('drag-over','folder-drop')}
   onDrop={e=>{e.preventDefault();e.stopPropagation();e.currentTarget.classList.remove('drag-over','folder-drop');const id=drag.current;if(!id||id===app.id)return;
    if(folder)send('start-folder-reorder',{folder,id,target:app.id});
    else if(pinned&&dropMode(e,app,folder)==='folder'){if(app.kind==='start-folder')send('start-folder-add',{id,folder:app.id});else send('start-folder-create',{apps:[app.id,id]});}
    else if(pinned)send('reorder',{id,target:app.id});}}
   onDragEnd={()=>{drag.current=null;document.querySelectorAll('.drag-over').forEach(e=>e.classList.remove('drag-over','folder-drop'));}}>
    {app.kind==='start-folder'?<span className="start-folder-icon">{app.apps.slice(0,4).map(id=>byId[id]&&<React.Fragment key={id}>{icon(byId[id])}</React.Fragment>)}</span>:icon(app)}<span>{app.name}</span></button>;
 const dialogKeys=e=>{if(e.key==='Tab'){const buttons=[...e.currentTarget.querySelectorAll('button:not(:disabled),input')];if(!buttons.length)return;const first=buttons[0],last=buttons[buttons.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
 const toastNode=toast&&<div role="alert" className="toast">{toast}</div>;
 const contextNode=context&&<div className="context-menu" role="menu" style={{left:Math.max(6,context.x),top:Math.max(6,context.y),maxHeight:innerHeight-Math.max(6,context.y)-8}} onKeyDown={e=>{if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const buttons=[...e.currentTarget.querySelectorAll('button')],i=buttons.indexOf(document.activeElement);buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowUp'?-1:1)+buttons.length)%buttons.length]?.focus();}}} onClick={e=>e.stopPropagation()}>
  <button onClick={()=>open(context.item)}>Open</button>
  {context.item.kind==='document'&&<button onClick={()=>{send('recent-location',{id:context.item.id});setContext(null);}}>Open file location</button>}
  {(context.item.actions||[]).map(action=><button key={action.id} onClick={()=>{send('app-action',{id:context.item.id,shortcut:action.id});setContext(null);}}>{action.name}</button>)}
  {data.mode==='start'&&context.item.kind==='start-folder'?<>
   <button onClick={()=>open(context.item)}>Rename folder</button>
   <button onClick={()=>{send('reorder',{id:context.item.id,target:data.pins[0]});setContext(null);}}>Move to first</button>
   <button onClick={()=>{send('start-folder-remove',{folder:context.item.id});setContext(null);}}>Move all apps out of folder</button>
  </>:data.mode==='start'&&!['path','document'].includes(context.item.kind)&&<>
   <button onClick={()=>pin(context.item,!pinnedApps.has(context.item.id))}>{pinnedApps.has(context.item.id)?'Unpin from Start':'Pin to Start'}</button>
   {context.folder&&<><button onClick={()=>pin(context.item,true)}>Move to Start</button><button onClick={()=>{send('start-folder-reorder',{folder:context.folder,id:context.item.id,target:folderById[context.folder].apps[0]});setContext(null);}}>Move to first in folder</button></>}
   {data.pins.includes(context.item.id)&&data.pins[0]!==context.item.id&&<button onClick={()=>{send('reorder',{id:context.item.id,target:data.pins[0]});setContext(null);}}>Move to first</button>}
   <button onClick={()=>{setFolderPicker(context.item.id);setContext(null);}}>Move to Start folder…</button>
   <button onClick={()=>{setAddTo(context.item);setContext(null);}}>Add to desktop group…</button>
  </>}
  {data.mode==='start'&&data.startStyle==='windows10'&&data.pins.includes(context.item.id)&&<div className="context-sizes" role="group" aria-label="Resize">
   {[['small','Small'],['medium','Medium'],['wide','Wide'],['large','Large']].map(([size,label])=><button key={size} aria-pressed={(data.startTiles?.[context.item.id]||'medium')===size} onClick={()=>{send('start-tile-size',{id:context.item.id,size});setContext(null);}}>{label}</button>)}
  </div>}
  {data.mode==='start'&&['windows11','tabbed','fullscreen'].includes(data.startStyle||'windows11')&&byId[context.item.id]&&!context.folder&&<>
   {activeTab?.apps.includes(context.item.id)&&<>
    <button onClick={()=>{send('start-tab',{operation:'remove',tab:activeTab.id,value:context.item.id});setContext(null);}}>Remove from {activeTab.name}</button>
    {activeTab.apps[0]!==context.item.id&&<button onClick={()=>{send('start-tab',{operation:'move',tab:activeTab.id,value:{id:context.item.id,target:activeTab.apps[0]}});setContext(null);}}>Move to first in {activeTab.name}</button>}
   </>}
   {options.tabs.filter(t=>!t.apps.includes(context.item.id)).map(t=><button key={t.id} onClick={()=>{send('start-tab',{operation:'add',tab:t.id,value:context.item.id});setContext(null);}}>Add to {t.name}</button>)}
  </>}
  {context.group&&!context.group.folder&&<button onClick={()=>{send('remove-item',{group:context.group.id,id:context.item.id});setContext(null);}}>Remove shortcut</button>}
 </div>;

 if(data.mode==='settings')return <Settings data={data} toast={toast} initialPage={page}/>;
 if(data.mode==='explorer')return <Explorer data={data} toast={toast}/>;
 if(data.mode==='notifications')return <NotificationCenter data={data} toast={toast}/>;
 if(data.mode==='quick')return <QuickSettings data={data} toast={toast}/>;
 if(data.mode==='group'){
  const g=data.group;
  return <main ref={root} className={'desktop-group'+(g.collapsed?' collapsed':'')} onClick={()=>setContext(null)}>
   <header className="group-titlebar" onMouseDown={e=>{if(e.button===0&&!e.target.closest('button'))send('move');}}>
    <Symbol name={g.folder?'folder':'grid'} size={16}/><strong>{g.title}</strong>
    <span className="count">{g.items.length}</span>
    <button className="icon-button" aria-label="Manage desktop groups" title="Manage group" onClick={()=>send('manage')}><Symbol name="more" size={18}/></button>
    <button className="icon-button collapse-button" aria-label={g.collapsed?'Expand group':'Collapse group'} onClick={()=>send('collapse',{group:g.id})}><Symbol name={g.collapsed?'down':'back'} size={16}/></button>
   </header>
   {!g.collapsed&&<><div className="group-content">
    {g.error&&<p className="empty">Folder unavailable. Choose a different folder in Desktop groups.</p>}
    <div className="group-grid">{g.items.map(app=>tile(app,{group:g}))}</div>
    {!g.items.length&&!g.error&&<button className="empty-add" onClick={()=>send('manage')}><Symbol name="plus"/><span>Add apps, files, or folders</span></button>}
    {g.overflow&&<p className="empty">Showing the first 200 items. Open the folder to see everything.</p>}
   </div><button className="resize-handle" title="Drag to resize" aria-label="Resize group" onMouseDown={e=>{if(e.button===0){e.preventDefault();send('resize');}}}><Symbol name="resize" size={15}/></button></>}
   {contextNode}{toastNode}
  </main>;
 }

 const footerMenuNode=footerMenu&&<SessionMenu kind={footerMenu} trigger={footerMenu==='account'?accountButton:powerButton} onClose={()=>setFooterMenu(null)} onAction={command=>{setFooterMenu(null);if(command==='accounts')send('settings',{page:'accounts'});else send('session-action',{command});}}/>;
 const overlayNodes=<>
  {currentFolder&&!folderPicker&&<div className="modal-backdrop" onClick={()=>setStartFolder(null)}><section className="picker start-folder-dialog" role="dialog" aria-modal="true" aria-label={currentFolder.name+' folder'} onClick={e=>e.stopPropagation()} onKeyDown={dialogKeys}>
   <div className="section-heading"><h2>{currentFolder.name}</h2><button className="icon-button" aria-label="Close folder" onClick={()=>setStartFolder(null)}><Symbol name="close"/></button></div>
   <form className="start-folder-name" onSubmit={e=>{e.preventDefault();send('start-folder-rename',{folder:currentFolder.id,name:folderName});}}><input aria-label="Folder name" maxLength={60} value={folderName} onChange={e=>setFolderName(e.target.value)}/><button className="small-button" type="submit">Save name</button></form>
   <div className="start-folder-apps">{currentFolder.apps.map(id=>byId[id]&&tile(byId[id],{folder:currentFolder.id}))}</div>
   {!currentFolder.apps.some(id=>byId[id])&&<p className="empty">The apps in this folder are currently unavailable.</p>}
   <p className="hint">Drag to reorder. Right-click an app to move it back to Start.</p>
   <button className="small-button" onClick={()=>{send('start-folder-remove',{folder:currentFolder.id});setStartFolder(null);}}>Move all apps out of folder</button>
  </section></div>}
  {folderPicker&&<div className="modal-backdrop" onClick={()=>setFolderPicker(null)}><section className="picker start-folder-picker" role="dialog" aria-modal="true" aria-label="Move to Start folder" onClick={e=>e.stopPropagation()} onKeyDown={dialogKeys}>
   <div className="section-heading"><h2>Move {byId[folderPicker]?.name} to a folder</h2><button className="icon-button" aria-label="Close folder picker" onClick={()=>setFolderPicker(null)}><Symbol name="close"/></button></div>
   {folders.filter(f=>!f.apps.includes(folderPicker)).length>0&&<div className="group-choices">{folders.filter(f=>!f.apps.includes(folderPicker)).map(f=><button key={f.id} onClick={()=>{send('start-folder-add',{id:folderPicker,folder:f.id});setFolderPicker(null);setStartFolder(null);}}><Symbol name="folder"/><span>{f.name}</span></button>)}</div>}
   <h3>Create a new folder with</h3><div className="picker-apps">{apps.filter(a=>a.id!==folderPicker).map(app=><button className="app-launch" key={app.id} onClick={()=>{send('start-folder-create',{apps:[folderPicker,app.id]});setFolderPicker(null);setStartFolder(null);}}>{icon(app)}<span>{app.name}</span></button>)}</div>
  </section></div>}
  {addTo&&<div className="modal-backdrop" onClick={()=>setAddTo(null)}><section className="picker" onClick={e=>e.stopPropagation()}><div className="section-heading"><h2>{addTo.group?'Add an app':'Add to desktop group'}</h2><button className="icon-button" aria-label="Close picker" onClick={()=>setAddTo(null)}><Symbol name="close"/></button></div>
   {addTo.group?<div className="picker-apps">{apps.map(app=><button className="app-launch" key={app.id} onClick={()=>{send('add-app',{group:addTo.group,id:app.id});setAddTo(null);}}>{icon(app)}<span>{app.name}</span><Symbol name="plus" size={16}/></button>)}</div>:<div className="group-choices">{data.groups.filter(g=>!g.folder).map(g=><button key={g.id} onClick={()=>{send('add-app',{group:g.id,id:addTo.id});setAddTo(null);}}><Symbol name="grid"/><span>{g.title}</span><Symbol name="plus" size={16}/></button>)}{!data.groups.some(g=>!g.folder)&&<p className="empty">Create a shortcut group in Desktop groups first.</p>}</div>}
  </section></div>}
 </>;
 const listKeys=e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key)||e.target.tagName==='INPUT')return;const buttons=[...e.currentTarget.querySelectorAll('.classic-item,.w10-item')],i=buttons.indexOf(document.activeElement);if(!buttons.length)return;e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:i<0?0:(i+(e.key==='ArrowUp'?-1:1)+buttons.length)%buttons.length]?.focus();};
 const classicRow=item=><button key={item.id} className={'classic-item'+(item.missing?' missing':'')} title={item.name+(item.missing?' — unavailable':'')}
   onClick={()=>open(item)} onContextMenu={e=>menu(e,item)} onKeyDown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))menu(e,item);}}>
   {item.kind==='start-folder'?<span className="classic-folder-icon"><Symbol name="folder" size={22}/></span>:icon(item)}<span>{item.name}</span></button>;
 const letterOf=app=>{const c=app.name.trim().charAt(0).toUpperCase();return /[A-Z]/.test(c)?c:'#';};
 const letters=[...new Set(apps.map(letterOf))];
 const w10Row=app=><button key={app.id} className="w10-item" title={app.name} onClick={()=>open(app)} onContextMenu={e=>menu(e,app)} onKeyDown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))menu(e,app);}}>{icon(app)}<span>{app.name}</span></button>;
 const letteredList=()=>letters.map(l=><section key={l} aria-label={l==='#'?'Other':l}><h3 className="w10-heading list-letter">{l}</h3>{apps.filter(a=>letterOf(a)===l).map(w10Row)}</section>);

 const pinnedSection=(showAllApps=true)=>{
     // Pinned and named tabs share one paged grid; Pinned keeps drag, folders and reorder.
     const items=(activeTab?activeTab.apps.map(id=>byId[id]):data.pins.map(id=>byId[id]||folderById[id])).filter(Boolean);
     const rows=pinRows+(options.showRecommended?0:2),perPage=rows*options.columns,pages=Math.max(1,Math.ceil(items.length/perPage)),current=Math.min(pinPage,pages-1);
     const choose=id=>{setPinTab(id);setPinPage(0);setTabName(null);};
     const saveName=()=>{if(nameCancelled.current){nameCancelled.current=false;return;}const name=tabName.value.trim();if(name)send('start-tab',tabName.id?{operation:'rename',tab:tabName.id,value:name}:{operation:'create',value:name});setTabName(null);};
     return <>
      <div className="section-heading pin-heading">
       <div className="pin-tabs" role="tablist" aria-label="Pinned tabs">
        {[{id:'pinned',name:'Pinned'},...options.tabs].map(t=>tabName?.id===t.id&&t.id!=='pinned'?null:<button key={t.id} role="tab" aria-selected={(activeTab?.id||'pinned')===t.id} onClick={()=>choose(t.id)} onDoubleClick={()=>t.id!=='pinned'&&setTabName({id:t.id,value:t.name})}>{t.name}</button>)}
        {tabName?<form className="pin-tab-name" onSubmit={e=>{e.preventDefault();saveName();}}><input autoFocus aria-label={tabName.id?'Tab name':'New tab name'} maxLength={40} value={tabName.value} onChange={e=>setTabName({...tabName,value:e.target.value})} onBlur={saveName} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();nameCancelled.current=true;setTabName(null);}}}/></form>
         :options.tabs.length<8&&<button className="icon-button pin-tab-add" aria-label="New tab" title="New tab" onClick={()=>setTabName({id:null,value:''})}><Symbol name="plus" size={15}/></button>}
       </div>
       <div className="recommended-actions">
        {activeTab&&!tabName&&<><button className="icon-button" aria-label={'Rename '+activeTab.name} title="Rename tab" onClick={()=>setTabName({id:activeTab.id,value:activeTab.name})}><Symbol name="more" size={16}/></button><button className="icon-button" aria-label={'Delete '+activeTab.name} title="Delete tab (keeps your apps)" onClick={()=>{send('start-tab',{operation:'delete',tab:activeTab.id});choose('pinned');}}><Symbol name="close" size={15}/></button></>}
        {showAllApps&&<button className="small-button" onClick={()=>setPage('all')}>All apps <Symbol name="arrow" size={13}/></button>}
       </div>
      </div>
      <div className="pin-pager">
       <div className="pins" aria-label={(activeTab?activeTab.name:'Pinned')+' apps'} style={{gridTemplateColumns:`repeat(${options.columns},minmax(0,1fr))`,minHeight:rows*76}}
        onKeyDown={e=>{if(e.key==='PageDown'||e.key==='PageUp'){e.preventDefault();setPinPage(Math.max(0,Math.min(pages-1,current+(e.key==='PageDown'?1:-1))));setTimeout(()=>document.querySelector('.pins .app-tile')?.focus(),0);}}}>
        {items.slice(current*perPage,(current+1)*perPage).map(item=>activeTab?tile(item):tile(item,{pinned:true}))}
        {!items.length&&<p className="empty">{activeTab?'Right-click an app and choose Add to '+activeTab.name+'.':'Open All apps and use the pin button to add your favorites.'}</p>}
       </div>
       {pages>1&&<div className="pin-pages" role="group" aria-label="Pinned pages">{Array.from({length:pages},(_,i)=><button key={i} aria-label={'Page '+(i+1)+' of '+pages} aria-current={i===current?'page':undefined} onClick={()=>setPinPage(i)}><i/></button>)}</div>}
      </div>
     </>;
 };
 const recommendedSection=options.showRecommended&&<><div className="section-heading recommended-heading"><h2>{recommended.length?'Recommended':'Quick access'}</h2><div className="recommended-actions">{data.recent.length>0&&<button className="small-button text-button" onClick={()=>setPage('recent')}>Recent apps <Symbol name="arrow" size={13}/></button>}<button className="small-button text-button" aria-label="Search and Start settings" onClick={()=>send('settings',{page:'search-start'})}><Symbol name="settings" size={16}/></button></div></div>
    <div className="recommended">{(recommended.length?recommended:data.places).map(item=><button className="recommended-item" key={item.id} title={item.name} onClick={()=>open(item)} onContextMenu={e=>menu(e,item)} onKeyDown={e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))menu(e,item);}}>{icon(item)}<span>{item.name}<small>{item.kind==='document'?'Recently opened':item.kind==='path'?'Open folder':'Opened from Start'}</small></span></button>)}</div></>;
 const searchInput=(className,label)=><div className={'search-box '+className}><Symbol name="search" size={16}/><input ref={search} aria-label={label} placeholder={label} value={query} onChange={e=>setQuery(e.target.value)}
   onKeyDown={e=>{if(query.trim())return;if(e.key==='ArrowDown'){e.preventDefault();document.querySelector('.start-shell .w10-item,.start-shell .pins .app-tile,.start-shell .launcher-canvas .app-tile')?.focus();}}}/>
   {query&&<button aria-label="Clear search" className="icon-button" onClick={()=>{setQuery('');search.current.focus();}}><Symbol name="close" size={15}/></button>}</div>;
 const sessionButtons=<>
   <button ref={accountButton} className="profile" title="Account options" aria-label="Account options" aria-haspopup="menu" aria-expanded={footerMenu==='account'} onClick={e=>{e.stopPropagation();setContext(null);setFooterMenu(footerMenu==='account'?null:'account');}}><span className="avatar">{data.avatar?<img src={data.avatar} alt=""/>:<Symbol name="user" size={19}/>}</span><span>{data.user}</span></button>
   <div className="footer-actions"><button className="icon-button" title="Settings" aria-label="Settings" onClick={()=>send('settings')}><Symbol name="settings" size={20}/></button><button ref={powerButton} className="icon-button" title="Power" aria-label="Power options" aria-haspopup="menu" aria-expanded={footerMenu==='power'} onClick={e=>{e.stopPropagation();setContext(null);setFooterMenu(footerMenu==='power'?null:'power');}}><Symbol name="power" size={20}/></button></div>
  </>;
 const shellProps=className=>({className:'start-shell '+className,ref:root,style:data.backdrop?{'--panel-backdrop':`url("${data.backdrop}")`}:undefined,onClick:()=>{setContext(null);setFooterMenu(null);}});

 if(data.startStyle==='tabbed'){
  // App style with tabs (Start11): the All apps column opens by default beside a tabbed app canvas.
  return <main {...shellProps('start-tabbed')}>
   <div className="tabbed-columns">
    <div className="tabbed-apps">
     {searchInput('tabbed-search','Search apps, files and settings')}
     {!query.trim()&&<div className="w10-list tabbed-list" aria-label="All apps" onKeyDown={listKeys}><h2 className="w10-heading">All apps</h2>{letteredList()}</div>}
    </div>
    <div className="tabbed-canvas start-body">{query.trim()?<UnifiedSearch query={query} input={search}/>:pinnedSection(false)}</div>
   </div>
   <footer className="start-footer">{sessionButtons}</footer>
   {footerMenuNode}{overlayNodes}{contextNode}{toastNode}
  </main>;
 }

 if(data.startStyle==='launcher'){
  // Launcher (Start11): a mobile-launcher look with a prominent account, search pill and large app canvas.
  const chips=[['pinned','Pinned'],['all','All apps'],...categories.map(c=>['category:'+c.name,c.name])];
  const chip=chips.some(([id])=>id===launcherChip)?launcherChip:'pinned';
  const canvas=chip==='pinned'?data.pins.map(id=>byId[id]||folderById[id]).filter(Boolean):chip==='all'?apps:categories.find(c=>'category:'+c.name===chip).apps;
  return <main {...shellProps('start-launcher')}>
   <header className="launcher-header">{sessionButtons}</header>
   {searchInput('launcher-search','Search apps, files and settings')}
   {query.trim()?<div className="launcher-results"><UnifiedSearch query={query} input={search}/></div>:<>
    <div className="launcher-chips" role="tablist" aria-label="App groups">{chips.map(([id,label])=><button key={id} role="tab" aria-selected={chip===id} onClick={()=>setLauncherChip(id)}>{label}</button>)}</div>
    <div className="launcher-canvas" aria-label={chips.find(([id])=>id===chip)[1]}>{canvas.map(item=>chip==='pinned'?tile(item,{pinned:true}):tile(item))}
     {!canvas.length&&<p className="empty">Choose All apps and use the pin button or right-click menu to pin your favorites.</p>}</div>
   </>}
   {footerMenuNode}{overlayNodes}{contextNode}{toastNode}
  </main>;
 }

 if(data.startStyle==='fullscreen'){
  // Full screen: the work area holds search, the A-Z list, paged pins and Recommended.
  return <main {...shellProps('start-fullscreen')}>
   <header className="fullscreen-header">{searchInput('fullscreen-search','Search apps, files and settings')}<div className="fullscreen-session">{sessionButtons}</div></header>
   {query.trim()?<div className="fullscreen-results start-body"><UnifiedSearch query={query} input={search}/></div>:<div className="fullscreen-body">
    <div className="w10-list fullscreen-list" aria-label="All apps" onKeyDown={listKeys}><h2 className="w10-heading">All apps</h2>{letteredList()}</div>
    <div className="fullscreen-canvas start-body">{pinnedSection(false)}{recommendedSection}</div>
   </div>}
   {footerMenuNode}{overlayNodes}{contextNode}{toastNode}
  </main>;
 }

 if(data.startStyle==='windows10'){
  // Windows 10 layout: a narrow rail, the full app list and resizable live-style tiles.
  const mostUsed=data.recent.map(id=>byId[id]).filter(Boolean).slice(0,6);
  const places=data.startPlaces||[];
  const railButton=(label,symbol,action,extra={})=><button className="w10-rail-button" title={label} aria-label={label} onClick={e=>{e.stopPropagation();action(e);}} {...extra}>{symbol}<span>{label}</span></button>;
  return <main className={'start-shell start-w10'+(railOpen?' rail-open':'')} style={data.backdrop?{'--panel-backdrop':`url("${data.backdrop}")`}:undefined} ref={root} onClick={()=>{setContext(null);setFooterMenu(null);setRailOpen(false);}}>
   <nav className="w10-rail" aria-label="Start">
    {railButton(railOpen?'Collapse':'Expand',<Symbol name="menu" size={18}/>,()=>setRailOpen(!railOpen),{'aria-expanded':railOpen})}
    <div className="w10-rail-bottom">
     {railButton(data.user,<span className="avatar">{data.avatar?<img src={data.avatar} alt=""/>:<Symbol name="user" size={16}/>}</span>,()=>{setRailOpen(false);setContext(null);setFooterMenu(footerMenu==='account'?null:'account');},{ref:accountButton,'aria-haspopup':'menu','aria-expanded':footerMenu==='account'})}
     {places.slice(1,3).map(p=><React.Fragment key={p.id}>{railButton(p.name,<Symbol name="folder" size={18}/>,()=>open(p))}</React.Fragment>)}
     {railButton('Settings',<Symbol name="settings" size={18}/>,()=>send('settings'))}
     {railButton('Power',<Symbol name="power" size={18}/>,()=>{setRailOpen(false);setContext(null);setFooterMenu(footerMenu==='power'?null:'power');},{ref:powerButton,'aria-haspopup':'menu','aria-expanded':footerMenu==='power'})}
    </div>
   </nav>
   <div className="w10-content">
    <div className="search-box w10-search"><Symbol name="search" size={16}/><input ref={search} aria-label="Type here to search" placeholder="Type here to search" value={query} onChange={e=>{setQuery(e.target.value);setLetterGrid(false);}}
     onKeyDown={e=>{if(query.trim())return;if(e.key==='ArrowDown'){e.preventDefault();document.querySelector('.w10-list .w10-item')?.focus();}}}/>
     {query&&<button aria-label="Clear search" className="icon-button" onClick={()=>{setQuery('');search.current.focus();}}><Symbol name="close" size={15}/></button>}
    </div>
    {query.trim()?<div className="w10-search-results"><UnifiedSearch query={query} input={search}/></div>:<div className="w10-columns">
     <div className="w10-list" aria-label="All apps" onKeyDown={listKeys}>
      {letterGrid?<div className="w10-letter-grid" role="group" aria-label="Jump to letter">{[...'#ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map(l=><button key={l} disabled={!letters.includes(l)} onClick={()=>{setLetterGrid(false);setTimeout(()=>{const h=document.getElementById('w10-letter-'+l),list=h?.closest('.w10-list');if(!h)return;list.scrollTop=h.offsetTop-list.offsetTop;h.focus({preventScroll:true});},0);}}>{l}</button>)}</div>:<>
       {mostUsed.length>0&&<><h2 className="w10-heading">Most used</h2>{mostUsed.map(w10Row)}</>}
       {letters.map(l=><section key={l} aria-label={l==='#'?'Other':l}>
        <button id={'w10-letter-'+l} className="w10-item w10-letter" aria-label={'Apps starting with '+(l==='#'?'other characters':l)+'. Show letters'} onClick={()=>setLetterGrid(true)}>{l}</button>
        {apps.filter(a=>letterOf(a)===l).map(w10Row)}
       </section>)}
      </>}
     </div>
     <div className="w10-tiles" aria-label="Pinned tiles">
      <h2 className="w10-heading">Pinned</h2>
      <div className="w10-tile-grid">{data.pins.map(id=>{const item=byId[id]||folderById[id];return item&&<div key={id} className={'w10-tile w10-'+(data.startTiles?.[id]||'medium')}>{tile(item,{pinned:true})}</div>;})}</div>
      {!data.pins.length&&<p className="empty">Right-click an app and choose Pin to Start to add a tile.</p>}
     </div>
    </div>}
   </div>
   {footerMenuNode}{overlayNodes}{contextNode}{toastNode}
  </main>;
 }

 if(data.startStyle==='windows7'||data.startStyle==='modern'){
  // Windows 7 layout: programs and search on the left, places and power on the right.
  // Modern (Start11's) keeps those columns in a dark, square Windows 10 skin, with
  // Pinned/All apps tabs and a flat alphabetical list in place of category folders.
  const modern=data.startStyle==='modern';
  const pinnedItems=data.pins.map(id=>byId[id]||folderById[id]).filter(Boolean);
  const frequent=data.recent.filter(id=>!data.pins.includes(id)).map(id=>byId[id]).filter(Boolean).slice(0,8);
  const places=data.startPlaces||[];
  const placeName=p=>p.path===places[0]?.path?data.user:p.name;
  const hover=name=>({onMouseEnter:()=>setPlaceHover(name),onFocus:()=>setPlaceHover(name),onBlur:()=>setPlaceHover(null)});
  return <main className={'start-shell start-classic'+(modern?' start-modern':'')} style={data.backdrop?{'--panel-backdrop':`url("${data.backdrop}")`}:undefined} ref={root} onClick={()=>{setContext(null);setFooterMenu(null);}}>
   <div className="classic-left">
    {modern&&!query.trim()&&<div className="modern-tabs" role="tablist" aria-label="Apps">{[['home','Pinned'],['all','All apps']].map(([id,label])=><button key={id} role="tab" aria-selected={(page==='all')===(id==='all')} onClick={()=>setPage(id)}>{label}</button>)}</div>}
    <div className="classic-programs" onKeyDown={listKeys}>
     {query.trim()?<UnifiedSearch query={query} input={search}/>:page==='all'?<div className="classic-list" aria-label={modern?'All apps':'All programs'}>
      {modern?apps.map(classicRow):categories.map(c=><React.Fragment key={c.name}>
       <button className="classic-item classic-category" aria-expanded={openCategory===c.name} onClick={()=>setOpenCategory(openCategory===c.name?null:c.name)}><span className="classic-folder-icon"><Symbol name="folder" size={22}/></span><span>{c.name}</span></button>
       {openCategory===c.name&&<div className="classic-nested">{c.apps.map(classicRow)}</div>}
      </React.Fragment>)}
     </div>:<div className="classic-list" aria-label="Pinned and frequent programs">
      {pinnedItems.map(classicRow)}
      {pinnedItems.length>0&&frequent.length>0&&<hr/>}
      {frequent.map(classicRow)}
      {!pinnedItems.length&&!frequent.length&&<p className="empty">Open {modern?'All apps':'All Programs'} and right-click an app to pin it here.</p>}
     </div>}
    </div>
    {!modern&&!query.trim()&&<button className="classic-all" onClick={()=>{setOpenCategory(null);setPage(page==='all'?'home':'all');}}>{page==='all'?<><Symbol name="back" size={14}/><span>Back</span></>:<><span>All Programs</span><Symbol name="arrow" size={14}/></>}</button>}
    <div className="search-box classic-search"><input ref={search} aria-label={modern?'Search apps, files and settings':'Search programs and files'} placeholder={modern?'Search apps, files and settings':'Search programs and files'} value={query} onChange={e=>setQuery(e.target.value)}
     onKeyDown={e=>{if(query.trim())return;if(e.key==='ArrowUp'){e.preventDefault();[...document.querySelectorAll('.classic-programs .classic-item')].pop()?.focus();}}}/>
     {query?<button aria-label="Clear search" className="icon-button" onClick={()=>{setQuery('');search.current.focus();}}><Symbol name="close" size={15}/></button>:<Symbol name="search" size={16}/>}
    </div>
   </div>
   <div className="classic-right">
    <button className="classic-picture" title="Account settings" aria-label="Account settings" onClick={()=>send('settings',{page:'accounts'})}>
     {placeHover?<Symbol name={placeHover} size={34}/>:data.avatar?<img src={data.avatar} alt=""/>:<Symbol name="user" size={34}/>}
    </button>
    <nav className="classic-places" aria-label="Places" onMouseLeave={()=>setPlaceHover(null)}>
     {places.map((p,index)=><button key={p.id} className={'classic-place'+(index===0?' strong':'')} {...hover('folder')} onClick={()=>open(p)}>{placeName(p)}</button>)}
     <hr/>
     <button className="classic-place" {...hover('grid')} onClick={()=>send('open-computer')}>Computer</button>
     <hr/>
     <button className="classic-place" {...hover('settings')} onClick={()=>send('settings')}>Settings</button>
     <button className="classic-place" {...hover('settings')} onClick={()=>send('settings',{page:'search-start'})}>Start settings</button>
    </nav>
    <div className="classic-power">
     <button className="classic-shutdown" onClick={e=>{e.stopPropagation();send('session-action',{command:'shutdown'});}}>{modern&&<Symbol name="power" size={15}/>}Shut down</button>
     <button ref={powerButton} className="classic-power-more" aria-label="Shut down options" aria-haspopup="menu" aria-expanded={footerMenu==='classic'} onClick={e=>{e.stopPropagation();setContext(null);setFooterMenu(footerMenu==='classic'?null:'classic');}}><Symbol name="arrow" size={13}/></button>
    </div>
   </div>
   {footerMenuNode}{overlayNodes}{contextNode}{toastNode}
  </main>;
 }

 return <main className="start-shell" style={data.backdrop?{'--panel-backdrop':`url("${data.backdrop}")`}:undefined} ref={root} onClick={()=>{setContext(null);setFooterMenu(null);}}>
  <div className="menu-main">
   <div className="search-box"><Symbol name="search" size={18}/><input ref={search} aria-label="Search apps, files and settings" placeholder="Search apps, files and settings" value={query} onChange={e=>{setQuery(e.target.value);setPage('home');}}
    onKeyDown={e=>{if(query.trim())return;if(e.key==='ArrowDown'){e.preventDefault();document.querySelector('.app-list button,.pins .app-tile')?.focus();}}}/>
    {query&&<button aria-label="Clear search" className="icon-button" onClick={()=>{setQuery('');search.current.focus();}}><Symbol name="close" size={15}/></button>}
   </div>
   <div className="start-body">
   {query.trim()?<UnifiedSearch query={query} input={search}/>:['all','category','recent'].includes(page)?<>
    <div className="section-heading"><h2>{query.trim()?'Search results':page==='category'?category:page==='recent'?'Recent':'All apps'}</h2><button className="small-button" onClick={()=>{setQuery('');setPage('home');}}><Symbol name="back" size={13}/> Back</button></div>
    <div className="app-list" aria-label="All applications">{matches.map(app=><div className="app-row" key={app.id} onContextMenu={e=>menu(e,app)}>
     <button className="app-launch" onClick={()=>open(app)}>{icon(app)}<span>{app.name}</span></button>
     <button className={'pin-button icon-button'+(pinnedApps.has(app.id)?' is-pinned':'')} aria-label={(pinnedApps.has(app.id)?'Unpin ':'Pin ')+app.name} title={pinnedApps.has(app.id)?'Unpin from Start':'Pin to Start'} onClick={()=>pin(app,!pinnedApps.has(app.id))}><Symbol name="pin" size={17}/></button>
    </div>)}{!matches.length&&<p className="empty">No apps found. Try a different name.</p>}</div>
   </>:page==='groups'?<>
    <div className="section-heading"><h2>Desktop groups</h2><button className="small-button" onClick={()=>setPage('home')}><Symbol name="back" size={13}/> Back</button></div>
    <div className="groups-manager">
     <div className="groups-toolbar"><p>Organize shortcuts on your desktop.</p><button className="small-button" onClick={()=>send('groups-visible',{value:!data.groupsVisible})}>{data.groupsVisible?'Hide groups':'Show groups'}</button></div>
     <form className="create-group" onSubmit={e=>{e.preventDefault();send('new-group',{title:newName||'New group'});setNewName('');}}>
      <input aria-label="New group name" placeholder="Name a new group" value={newName} onChange={e=>setNewName(e.target.value)} maxLength={60}/><button className="small-button primary" type="submit"><Symbol name="plus" size={15}/> Create</button>
     </form>
     <button className="folder-group-button" onClick={()=>send('new-group',{folder:true})}><Symbol name="folder" size={18}/><span>Show a folder on the desktop</span><Symbol name="plus" size={16}/></button>
     {data.groups.map(g=><section className="group-card" key={g.id}>
      <div className="group-card-heading"><Symbol name={g.folder?'folder':'grid'} size={18}/>
       {rename===g.id?<input aria-label="Group name" autoFocus defaultValue={g.title} maxLength={60} onBlur={e=>{send('rename-group',{group:g.id,title:e.target.value});setRename(null);}} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}}/>:<button className="rename-title" title="Rename group" onClick={()=>setRename(g.id)}>{g.title}</button>}
       <span className="count">{g.items.length} items</span><button className="icon-button" title="Remove group (keeps your files)" aria-label={'Remove '+g.title} onClick={()=>send('remove-group',{group:g.id})}><Symbol name="close" size={16}/></button>
      </div>
      {g.folder?<div className="folder-path"><span title={g.folder}>{g.folder}</span><button className="small-button" onClick={()=>send('open-path',{path:g.folder})}>Open folder</button></div>:<>
       <div className="mini-items">{g.items.map(i=><div key={i.id} title={i.name}>{icon(i)}<button title={'Remove '+i.name+' shortcut'} aria-label={'Remove '+i.name+' shortcut'} onClick={()=>send('remove-item',{group:g.id,id:i.id})}>×</button></div>)}</div>
       <div className="group-actions"><button className="small-button" onClick={()=>setAddTo({group:g.id})}>Add app</button><button className="small-button" onClick={()=>send('add-path',{group:g.id})}>Add file</button><button className="small-button" onClick={()=>send('add-path',{group:g.id,folder:true})}>Add folder</button></div>
      </>}
     </section>)}
     <p className="hint">Drag a group’s title to move it. Drag its lower-right corner to resize.<br/>Win + Shift + F brings your groups above open windows.</p>
    </div>
   </>:<>
    {pinnedSection()}
    {recommendedSection}
    <section className="start-all-section" aria-label="All applications by category">
     <div className="section-heading"><h2>All</h2><label className="app-view">View: <select aria-label="App view" value={appView} onChange={e=>setAppView(e.target.value)}><option>Category</option><option>Grid</option><option>List</option></select></label></div>
     {appView==='Category'?<div className="app-categories">{categories.map(c=><button className="app-category" key={c.name} aria-label={'Open '+c.name+' apps'} onClick={()=>{setCategory(c.name);setPage('category');}}><span className="category-preview">{c.apps.slice(0,4).map(app=><span key={app.id}>{icon(app)}</span>)}</span><span>{c.name}</span></button>)}</div>:appView==='Grid'?<div className="all-app-grid">{apps.map(app=>tile(app))}</div>:<div className="all-app-list">{apps.map(app=><button className="app-launch" key={app.id} onClick={()=>open(app)} onContextMenu={e=>menu(e,app)}>{icon(app)}<span>{app.name}</span></button>)}</div>}
    </section>
   </>}
   </div>
  </div>
  <footer className="start-footer"><button ref={accountButton} className="profile" title="Account options" aria-label="Account options" aria-haspopup="menu" aria-expanded={footerMenu==='account'} onClick={e=>{e.stopPropagation();setContext(null);setFooterMenu(footerMenu==='account'?null:'account');}}><span className="avatar">{data.avatar?<img src={data.avatar} alt=""/>:<Symbol name="user" size={19}/>}</span><span>{data.user}</span></button>
   <div className="footer-actions"><button className="icon-button" title="Desktop groups" aria-label="Desktop groups" onClick={()=>{setPage('groups');setQuery('');}}><Symbol name="grid" size={20}/></button><button className="icon-button" title="Settings" aria-label="Settings" onClick={()=>send('settings')}><Symbol name="settings" size={20}/></button><button ref={powerButton} className="icon-button" title="Power" aria-label="Power options" aria-haspopup="menu" aria-expanded={footerMenu==='power'} onClick={e=>{e.stopPropagation();setContext(null);setFooterMenu(footerMenu==='power'?null:'power');}}><Symbol name="power" size={20}/></button></div>
  </footer>
  {footerMenuNode}
  {overlayNodes}
  {contextNode}{toastNode}
 </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
