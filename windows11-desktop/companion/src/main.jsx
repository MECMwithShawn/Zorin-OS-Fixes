import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {Explorer} from './explorer.jsx';
import './explorer.css';
import {Settings} from './settings.jsx';
import {QuickSettings,NotificationCenter} from './flyouts.jsx';
import './window-chrome.css';

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
  resize:<path d="m9 21 12-12M15 21l6-6"/>};
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.grid}</svg>;
}

function SessionMenu({kind,trigger,onClose,onAction}) {
 const menu=useRef(null);
 useEffect(()=>{menu.current?.querySelector('button')?.focus();},[kind]);
 const items=kind==='account'
  ?[['user','Account settings','accounts'],['lock','Lock','lock'],['switchUser','Switch user','switch-user'],['logout','Sign out','sign-out']]
  :[['sleep','Sleep','sleep'],['power','Shut down','shutdown'],['restart','Restart','restart']];
 return <div ref={menu} className={'power-menu session-menu '+kind+'-menu'} role="menu" aria-label={kind==='account'?'Account menu':'Power menu'} onClick={e=>e.stopPropagation()} onKeyDown={e=>{
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onClose();trigger.current?.focus();}
  if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const buttons=[...menu.current.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowUp'?-1:1)+buttons.length)%buttons.length]?.focus();}
 }}>
 {items.map(([icon,label,action])=><button role="menuitem" key={action} onClick={()=>onAction(action)}><Symbol name={icon} size={18}/>{label}</button>)}
 </div>;
}

function App(){
 const [data,setData]=useState(null),[page,setPage]=useState('home'),[query,setQuery]=useState('');
 const [category,setCategory]=useState(null),[appView,setAppView]=useState('Category');
 const [context,setContext]=useState(null),[toast,setToast]=useState(''),[footerMenu,setFooterMenu]=useState(null);
 const [addTo,setAddTo]=useState(null),[newName,setNewName]=useState(''),[rename,setRename]=useState(null);
 const search=useRef(null),drag=useRef(null),root=useRef(null);
 const accountButton=useRef(null),powerButton=useRef(null);
 useEffect(()=>{
  window.receive=message=>{
   window.dispatchEvent(new CustomEvent('desktop-message',{detail:message}));
   if(message.type==='state'){window.desktopState=message.data;setData(message.data);}
   if(message.type==='show'){setPage(message.page||'home');setQuery('');setContext(null);setAddTo(null);setFooterMenu(null);setCategory(null);setTimeout(()=>search.current?.focus(),40);}
   if(message.type==='error'||message.type==='notice'){setToast(message.message);setTimeout(()=>setToast(''),5000);}
  };
  send('ready');
  return ()=>delete window.receive;
 },[]);
 useEffect(()=>{
  const close=e=>{if(e.key==='Escape'){setContext(null);setFooterMenu(null);setAddTo(null);} };
  document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);
 },[]);
 if(!data)return <div className="loading">Opening your desktop…</div>;
 const apps=data.apps||[];const byId=Object.fromEntries(apps.map(a=>[a.id,a]));
 const categoryFor=app=>{const kinds=app.categories||[];return [['Accessibility','Accessibility'],['Graphics','Creativity'],['Development','Developer Tools'],['AudioVideo','Entertainment'],['Game','Games'],['Office','Productivity'],['Network','Internet'],['Education','Education'],['Settings','System Tools'],['System','System Tools'],['Utility','Utilities']].find(([key])=>kinds.includes(key))?.[1]||'Other';};
 const categories=[...new Set(apps.map(categoryFor))].sort().map(name=>({name,apps:apps.filter(a=>categoryFor(a)===name)}));
 const visibleApps=page==='category'?apps.filter(a=>categoryFor(a)===category):page==='recent'?data.recent.map(id=>byId[id]).filter(Boolean):apps;
 const matches=visibleApps.filter(a=>(a.name+' '+a.description).toLowerCase().includes(query.trim().toLowerCase()));
 const pin=(app,value)=>{send('pin',{id:app.id,value});setContext(null);};
 const open=item=>{send(item.kind==='path'?'open-path':'launch',item.kind==='path'?{path:item.path}:{id:item.id});setContext(null);};
 const menu=(e,item,group)=>{e.preventDefault();e.stopPropagation();setContext({x:Math.min(e.clientX,innerWidth-226),y:Math.min(e.clientY,innerHeight-186),item,group});};
 const icon=item=><img className="app-icon" src={item.icon} alt="" draggable="false" onError={e=>{e.currentTarget.src='zorin11://icon/file';}}/>;
 const tile=(app,{pinned=false,group=null}={})=><button key={app.id} className={'app-tile'+(app.missing?' missing':'')} title={app.name+(app.missing?' — unavailable':'')}
   onClick={()=>open(app)} onContextMenu={e=>menu(e,app,group)}
   draggable={pinned} onDragStart={e=>{drag.current=app.id;e.dataTransfer.setData('text/plain',app.id);e.dataTransfer.effectAllowed='move';}}
   onDragOver={e=>{if(pinned){e.preventDefault();e.currentTarget.classList.add('drag-over');}}}
   onDragLeave={e=>e.currentTarget.classList.remove('drag-over')}
   onDrop={e=>{e.preventDefault();e.currentTarget.classList.remove('drag-over');if(pinned)send('reorder',{id:drag.current||e.dataTransfer.getData('text/plain'),target:app.id});}}
   onDragEnd={()=>{drag.current=null;document.querySelectorAll('.drag-over').forEach(e=>e.classList.remove('drag-over'));}}>
    {icon(app)}<span>{app.name}</span></button>;
 const toastNode=toast&&<div role="alert" className="toast">{toast}</div>;
 const contextNode=context&&<div className="context-menu" role="menu" style={{left:Math.max(6,context.x),top:Math.max(6,context.y)}} onClick={e=>e.stopPropagation()}>
  <button onClick={()=>open(context.item)}>Open</button>
  {data.mode==='start'&&context.item.kind!=='path'&&<>
   <button onClick={()=>pin(context.item,!data.pins.includes(context.item.id))}>{data.pins.includes(context.item.id)?'Unpin from Start':'Pin to Start'}</button>
   {data.pins.includes(context.item.id)&&data.pins[0]!==context.item.id&&<button onClick={()=>{send('reorder',{id:context.item.id,target:data.pins[0]});setContext(null);}}>Move to first</button>}
   <button onClick={()=>{setAddTo(context.item);setContext(null);}}>Add to desktop group…</button>
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

 return <main className="start-shell" style={data.backdrop?{'--panel-backdrop':`url("${data.backdrop}")`}:undefined} ref={root} onClick={()=>{setContext(null);setFooterMenu(null);}}>
  <div className="menu-main">
   <div className="search-box"><Symbol name="search" size={18}/><input ref={search} aria-label="Search apps" placeholder="Search your apps" value={query} onChange={e=>{setQuery(e.target.value);setPage('home');}}
    onKeyDown={e=>{if(e.key==='Enter'&&query.trim()&&matches[0])open(matches[0]);if(e.key==='ArrowDown'){e.preventDefault();document.querySelector('.app-list button,.pins .app-tile')?.focus();}}}/>
    {query&&<button aria-label="Clear search" className="icon-button" onClick={()=>{setQuery('');search.current.focus();}}><Symbol name="close" size={15}/></button>}
   </div>
   <div className="start-body">
   {query.trim()||['all','category','recent'].includes(page)?<>
    <div className="section-heading"><h2>{query.trim()?'Search results':page==='category'?category:page==='recent'?'Recent':'All apps'}</h2><button className="small-button" onClick={()=>{setQuery('');setPage('home');}}><Symbol name="back" size={13}/> Back</button></div>
    <div className="app-list" aria-label="All applications">{matches.map(app=><div className="app-row" key={app.id} onContextMenu={e=>menu(e,app)}>
     <button className="app-launch" onClick={()=>open(app)}>{icon(app)}<span>{app.name}</span></button>
     <button className={'pin-button icon-button'+(data.pins.includes(app.id)?' is-pinned':'')} aria-label={(data.pins.includes(app.id)?'Unpin ':'Pin ')+app.name} title={data.pins.includes(app.id)?'Unpin from Start':'Pin to Start'} onClick={()=>pin(app,!data.pins.includes(app.id))}><Symbol name="pin" size={17}/></button>
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
    <div className="section-heading"><h2>Pinned</h2><button className="small-button" onClick={()=>setPage('all')}>All apps <Symbol name="arrow" size={13}/></button></div>
    <div className="pins">{data.pins.map(id=>byId[id]&&tile(byId[id],{pinned:true}))}{!data.pins.length&&<p className="empty">Open All apps and use the pin button to add your favorites.</p>}</div>
    <div className="section-heading recommended-heading"><h2>{data.recent.length?'Recent':'Quick access'}</h2>{data.recent.length>0&&<button className="small-button text-button" onClick={()=>setPage('recent')}>Show all <Symbol name="arrow" size={13}/></button>}</div>
    <div className="recommended">{data.recent.length?data.recent.slice(0,6).map(id=>byId[id]&&<button className="recommended-item" key={id} onClick={()=>open(byId[id])}>{icon(byId[id])}<span>{byId[id].name}<small>Opened from Start</small></span></button>):data.places.map(p=><button className="recommended-item" key={p.id} onClick={()=>open(p)}>{icon(p)}<span>{p.name}<small>Open folder</small></span></button>)}</div>
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
  {footerMenu&&<SessionMenu kind={footerMenu} trigger={footerMenu==='account'?accountButton:powerButton} onClose={()=>setFooterMenu(null)} onAction={command=>{setFooterMenu(null);if(command==='accounts')send('settings',{page:'accounts'});else send('session-action',{command});}}/>}
  {addTo&&<div className="modal-backdrop" onClick={()=>setAddTo(null)}><section className="picker" onClick={e=>e.stopPropagation()}><div className="section-heading"><h2>{addTo.group?'Add an app':'Add to desktop group'}</h2><button className="icon-button" aria-label="Close picker" onClick={()=>setAddTo(null)}><Symbol name="close"/></button></div>
   {addTo.group?<div className="picker-apps">{apps.map(app=><button className="app-launch" key={app.id} onClick={()=>{send('add-app',{group:addTo.group,id:app.id});setAddTo(null);}}>{icon(app)}<span>{app.name}</span><Symbol name="plus" size={16}/></button>)}</div>:<div className="group-choices">{data.groups.filter(g=>!g.folder).map(g=><button key={g.id} onClick={()=>{send('add-app',{group:g.id,id:addTo.id});setAddTo(null);}}><Symbol name="grid"/><span>{g.title}</span><Symbol name="plus" size={16}/></button>)}{!data.groups.some(g=>!g.folder)&&<p className="empty">Create a shortcut group in Desktop groups first.</p>}</div>}
  </section></div>}
  {contextNode}{toastNode}
 </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
