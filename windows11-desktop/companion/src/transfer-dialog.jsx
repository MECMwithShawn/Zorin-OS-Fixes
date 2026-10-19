import React,{useEffect,useRef,useState} from 'react';
const send=(action,payload={})=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action,...payload}));
const bytes=n=>n>=1073741824?(n/1073741824).toFixed(1)+' GB':n>=1048576?(n/1048576).toFixed(1)+' MB':n>=1024?(n/1024).toFixed(1)+' KB':n+' bytes';
const names={replace:'Replace the file',merge:'Merge folders',skip:'Skip', 'keep-both':'Keep both',retry:'Retry'};
export function TransferDialog({job,onDismiss}){
 const [all,setAll]=useState(false),root=useRef(null);
 const command=(action,payload={})=>send('file-transfer-'+action,{id:job.id,...payload});
 const question=job.problem;
 useEffect(()=>{setAll(false);root.current?.querySelector('button')?.focus();},[job.id,question?.id,job.active]);
 const title=job.state==='conflict'?'Replace or skip files':job.state==='error'?'Unable to transfer item':job.state==='failed'?'Transfer failed':job.state==='cancelled'?'Transfer cancelled':job.state==='completed'?'Transfer complete':job.paused?'Transfer paused':job.state==='preparing'?'Preparing transfer…':job.cut?'Moving items':'Copying items';
 const percent=!job.active&&job.state==='completed'?100:job.totalBytes?Math.min(99,Math.floor(job.doneBytes/job.totalBytes*100)):job.totalItems?Math.min(99,Math.floor(job.doneItems/job.totalItems*100)):0;
 const dismiss=()=>{command('dismiss');onDismiss();};
 return <div className="file-modal transfer-backdrop" onClick={e=>e.stopPropagation()}><section ref={root} className="transfer-dialog" role="dialog" aria-modal="true" aria-label="File transfer" onKeyDown={e=>{
  e.stopPropagation();
  if(e.key==='Escape'){e.preventDefault();job.active?command('cancel'):dismiss();}
  if(e.key==='Tab'){const nodes=[...root.current.querySelectorAll('button:not(:disabled),input')],first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}
 }}><h2>{title}</h2><div className="transfer-body">
 <p className="transfer-destination">{job.cut?'Moving':'Copying'} to <strong>{job.destination}</strong></p>
 <div className="transfer-progress"><strong>{percent}%</strong><progress aria-label="Transfer progress" max="100" value={percent}/></div>
 <p className="transfer-current" title={job.current}>{job.current}</p>
 <p className="transfer-stats">{bytes(job.doneBytes)} of {bytes(job.totalBytes)} · {job.completed} completed · {job.skipped} skipped{job.state==='running'&&!job.paused?' · '+bytes(job.doneBytes/job.elapsed)+'/s':''}</p>
 {question?.source&&<div className="transfer-conflict"><h3>{question.type==='conflict'?'The destination already contains “'+question.target.name+'”.':question.source.name}</h3>{question.message&&<p role="alert">{question.message}</p>}
 <dl><dt>From</dt><dd>{question.source.path}{question.source.size!=null&&<small>{bytes(question.source.size)} · {new Date(question.source.modified*1000).toLocaleString()}</small>}</dd><dt>To</dt><dd>{question.target.path}{question.target.size!=null&&<small>{bytes(question.target.size)} · {new Date(question.target.modified*1000).toLocaleString()}</small>}</dd></dl>
 <div className="transfer-choices">{question.choices.map(choice=><button key={choice} onClick={()=>command('answer',{question:question.id,choice,all})}>{names[choice]}</button>)}</div>
 {question.type==='conflict'&&<label className="transfer-apply"><input type="checkbox" checked={all} onChange={e=>setAll(e.target.checked)}/> Use this choice for remaining {question.source.kind==='folder'?'folder':'file'} conflicts</label>}
 </div>}
 {job.state==='failed'&&<p role="alert">{question?.message}</p>}
 {(job.state==='cancelled'||job.skipped>0)&&<p className="transfer-note">Completed items remain in the destination. Skipped and unfinished source items are retained.</p>}
 {!!job.warnings?.length&&<div role="alert">{job.warnings.map((w,i)=><p key={i}>{w}</p>)}</div>}
 </div><div className="dialog-buttons">{job.active?<>{['running','preparing'].includes(job.state)&&<button onClick={()=>command('pause',{value:!job.paused})}>{job.paused?'Resume':'Pause'}</button>}<button onClick={()=>command('cancel')}>Cancel transfer</button></>:<button className="primary" onClick={dismiss}>Close</button>}</div>
 </section></div>;
}
