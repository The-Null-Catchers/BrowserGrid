'use client';
import {useEffect, useRef, useState} from 'react';
import {ExternalLink, ImageIcon, Film} from 'lucide-react';

export type RunArtifact = {id:string;job_id:string;name:string;kind:string;size:number};

function MediaArtifact({artifact, download}: {artifact:RunArtifact;download:(artifact:RunArtifact)=>void}) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const request = useRef<AbortController|null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const image = artifact.kind === 'screenshot' && /\.(png|jpe?g|webp)$/i.test(artifact.name);
  const video = artifact.kind === 'video' && /\.(webm|mp4)$/i.test(artifact.name);
  async function preview() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);setError('');setUrl('');
    try {
      const response = await fetch(`/api/v1/artifacts/${artifact.id}/download`, {credentials:'include',signal:controller.signal});
      if (!response.ok) throw new Error(response.status === 410 ? 'This artifact has expired.' : 'Unable to authorize this preview.');
      const data = await response.json() as {url:string};
      if (!controller.signal.aborted) setUrl(data.url);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Preview unavailable.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  return <article className={`artifact mediaArtifact${expanded?' expanded':''}`}>
    <div className="artifactMeta">{image?<ImageIcon size={18}/>:video?<Film size={18}/>:<ExternalLink size={18}/>}<strong>{artifact.name}</strong><small>{artifact.kind} · {(artifact.size/1024).toFixed(1)} KB · job {artifact.job_id.slice(0,8)}</small></div>
    {(image||video)&&<button className="secondary" disabled={loading} onClick={preview}>{loading?'Loading preview…':url||error?'Refresh preview':'Preview '+(image?'screenshot':'video')}</button>}
    {error&&<p role="alert">{error}</p>}
    {url&&image&&<><img src={url} alt={`Screenshot: ${artifact.name}`} className="screenshotPreview" onError={()=>{setUrl('');setError('Image could not load. Refresh the preview to renew its access link.');}}/><button className="textButton" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Collapse screenshot':'Expand screenshot'}</button></>}
    {url&&video&&<video src={url} controls preload="metadata" aria-label={`Recording: ${artifact.name}`} onError={()=>{setUrl('');setError('Video could not load. Refresh the preview to renew its access link.');}}/>}
    <button className="textButton" onClick={()=>download(artifact)}>Download artifact ↗</button>
  </article>;
}

export function ArtifactPanel({tab, artifacts, download}: {tab:string;artifacts:RunArtifact[];download:(artifact:RunArtifact)=>void}) {
  const visible = artifacts.filter(a=>tab==='Artifacts'||tab==='Screenshots'&&a.kind==='screenshot'||tab==='Videos'&&a.kind==='video'||tab==='Traces'&&a.kind==='trace'||tab==='Network'&&a.name.endsWith('network.json'));
  return <section className="panel"><div className="panelHeader"><h2>{tab}</h2><small>Private artifacts · access links expire after 120 seconds</small></div><div className="artifactGrid">{visible.map(artifact=><MediaArtifact key={artifact.id} artifact={artifact} download={download}/>)}</div>{!visible.length&&<div className="empty small"><p>No {tab==='Artifacts'?'artifacts':tab.toLowerCase()} have been uploaded for this run.</p></div>}</section>;
}
