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
  const accessibility = artifact.name.endsWith('accessibility.json');
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
    {accessibility&&<button className="secondary" onClick={preview} disabled={loading}>{loading?'Loading report…':'View accessibility report'}</button>}
    {url&&accessibility&&<a href={url} target="_blank" rel="noopener noreferrer">Open accessibility JSON ↗</a>}
    {(image||video)&&<button className="secondary" disabled={loading} onClick={preview}>{loading?'Loading preview…':url||error?'Refresh preview':'Preview '+(image?'screenshot':'video')}</button>}
    {error&&<p role="alert">{error}</p>}
    {url&&image&&<><img src={url} alt={`Screenshot: ${artifact.name}`} className="screenshotPreview" onError={()=>{setUrl('');setError('Image could not load. Refresh the preview to renew its access link.');}}/><button className="textButton" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Collapse screenshot':'Expand screenshot'}</button></>}
    {url&&video&&<video src={url} controls preload="metadata" aria-label={`Recording: ${artifact.name}`} onError={()=>{setUrl('');setError('Video could not load. Refresh the preview to renew its access link.');}}/>}
    <button className="textButton" onClick={()=>download(artifact)}>Download artifact ↗</button>
  </article>;
}

export function ArtifactPanel({tab, artifacts, download}: {tab:string;artifacts:RunArtifact[];download:(artifact:RunArtifact)=>void}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [sort, setSort] = useState('name');
  const [job, setJob] = useState('all');
  const [size, setSize] = useState('all');
  const matchingTab = artifacts.filter(a=>tab==='Artifacts'||tab==='Screenshots'&&a.kind==='screenshot'||tab==='Videos'&&a.kind==='video'||tab==='Traces'&&a.kind==='trace'||tab==='Network'&&a.name.endsWith('network.json'));
  const kinds = [...new Set(matchingTab.map(a=>a.kind))].sort();
  const jobs = [...new Set(matchingTab.map(a=>a.job_id))].sort();
  const filtersActive = query.trim()!=='' || kind!=='all' || job!=='all' || size!=='all' || sort!=='name';
  const visible = matchingTab.filter(a=>(job==='all'||a.job_id===job)&&(kind==='all'||a.kind===kind)&&(size==='all'||(size==='small'?a.size<1024*1024:size==='medium'?a.size>=1024*1024&&a.size<10*1024*1024:a.size>=10*1024*1024))&&(`${a.name} ${a.job_id} ${a.kind}`).toLowerCase().includes(query.trim().toLowerCase())).sort((a,b)=>sort==='size-desc'?b.size-a.size||a.name.localeCompare(b.name):sort==='size-asc'?a.size-b.size||a.name.localeCompare(b.name):sort==='name-desc'?b.name.localeCompare(a.name):a.name.localeCompare(b.name));
  return <section className="panel"><div className="panelHeader"><h2>{tab}</h2><small>Private artifacts · access links expire after 120 seconds</small></div>{matchingTab.length>0&&<div className="artifactFilters"><label>Search artifacts<input aria-label="Search artifacts" placeholder="Filename, job ID, or type" value={query} onChange={e=>setQuery(e.target.value)}/></label>{tab==='Artifacts'&&<label>Artifact type<select aria-label="Artifact type" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All types</option>{kinds.map(k=><option key={k} value={k}>{k}</option>)}</select></label>}{jobs.length>1&&<label>Browser job<select aria-label="Filter by browser job" value={job} onChange={e=>setJob(e.target.value)}><option value="all">All jobs</option>{jobs.map(id=><option key={id} value={id}>{id.slice(0,12)}</option>)}</select></label>}<label>File size<select aria-label="Filter by file size" value={size} onChange={e=>setSize(e.target.value)}><option value="all">All sizes</option><option value="small">Under 1 MB</option><option value="medium">1–10 MB</option><option value="large">10 MB or larger</option></select></label><label>Sort artifacts<select aria-label="Sort artifacts" value={sort} onChange={e=>setSort(e.target.value)}><option value="name">Filename A–Z</option><option value="name-desc">Filename Z–A</option><option value="size-desc">Largest first</option><option value="size-asc">Smallest first</option></select></label><small role="status" aria-live="polite">Showing {visible.length} of {matchingTab.length} artifacts</small>{filtersActive&&<button className="textButton" type="button" onClick={()=>{setQuery('');setKind('all');setJob('all');setSize('all');setSort('name');}}>Clear filters</button>}</div>}<div className="artifactGrid">{visible.map(artifact=><MediaArtifact key={artifact.id} artifact={artifact} download={download}/>)}</div>{!visible.length&&<div className="empty small"><p>{matchingTab.length?'No artifacts match the current filters.':`No ${tab==='Artifacts'?'artifacts':tab.toLowerCase()} have been uploaded for this run.`}</p></div>}</section>;
}
