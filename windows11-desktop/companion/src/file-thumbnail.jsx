import React,{useEffect,useRef,useState} from 'react';
import './file-thumbnail.css';

// Limit active image requests, including on WebKit versions without native lazy loading.
const waiting=[];let active=0;
function pump(){while(active<4&&waiting.length){const ticket=waiting.shift();if(ticket.done)continue;ticket.started=true;active++;ticket.start();}}
function enqueue(start){
 const ticket={start,started:false,done:false};waiting.push(ticket);pump();
 return()=>{if(ticket.done)return;ticket.done=true;if(ticket.started)active--;else{const i=waiting.indexOf(ticket);if(i>=0)waiting.splice(i,1);}pump();};
}
export function canThumbnail(item){return !item.folder&&/\.(jpe?g|png|webp|gif|bmp|tiff?)$/i.test(item.path||'');}

export function FileThumbnail({item,size,fallback}){
 const ref=useRef(null),release=useRef(()=>{}),[visible,setVisible]=useState(false),[ready,setReady]=useState(''),[failed,setFailed]=useState(''),[loaded,setLoaded]=useState('');
 const src='zorin11://thumbnail/'+encodeURIComponent(item.path)+'?v='+encodeURIComponent(JSON.stringify([item.modified,item.size]));
 useEffect(()=>{
  if(!('IntersectionObserver' in window)){setVisible(true);return;}
  const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){setVisible(true);observer.disconnect();}},
   {root:ref.current.closest('.explorer-files'),rootMargin:'120px'});
  observer.observe(ref.current);return()=>observer.disconnect();
 },[item.path]);
 useEffect(()=>{
  if(!visible)return;
  const done=enqueue(()=>setReady(src));release.current=done;
  return done;
 },[src,visible]);
 return <span ref={ref} className="file-thumbnail" style={{width:size,height:size,maxHeight:'none',position:'relative',display:'inline-flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
  {(loaded!==src||failed===src)&&fallback}
  {ready===src&&failed!==src&&<img className="photo-thumbnail" src={src} width={size} height={size} alt="" aria-hidden="true" draggable="false" style={{objectFit:'contain',borderRadius:3,position:'absolute',inset:0,opacity:loaded===src?1:0}}
   onLoad={()=>{setLoaded(src);release.current();}} onError={()=>{setFailed(src);release.current();}}/>}
 </span>;
}
