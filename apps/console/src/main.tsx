import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDownToLine, ArrowRight, Check, CheckCheck, ChevronRight, CircleHelp, Clock3, FileText, Inbox, Layers3, LayoutGrid, Link2, ListChecks, LoaderCircle, MessageSquare, Plus, Search, Settings2, ShieldCheck, Sparkles, TriangleAlert, X } from 'lucide-react';
import './style.css';
import feyaWordmark from './feya-wordmark.svg';
import Conversation from './Conversation';
import './brand.css';

type Phase = string;
type Fact = {key: string; value: string; evidence_id: string; quote: string};
type Action = {id: string; capability: string; payload: Record<string,string>; status: string; digest: string; policy_reasons: string[]; provider_ref: string | null};
type Case = {id: string; pack_id: string; customer_email: string; subject: string; phase: Phase; version: number; summary: string; missing: string[]; next_action: string; facts: Record<string,Fact>; created_at: string; completion_kind: string | null};
type Detail = Case & {actions: Action[]; evidence: {id: string; source_uri: string; content: {body: string; sender: string; subject: string}; created_at: string}[]; timeline: {id: string; kind: string; actor: string; created_at: string; detail: Record<string, unknown>}[]; runs: {id: string; model: string; role: string; status: string; usage: {input_tokens: number | null; output_tokens: number | null}}[]; verifications: {id: string; passed: boolean; checked_fields: string[]}[]};
type Pack = {id: string; name: string; description: string; version: string; required_facts: {key: string; label: string}[]; rates: Record<string,{label: string; unit_price: string}>; fixture: {sender: string; subject: string; body: string}};
type Workspace = {name: string; mode: string; runner: string; model: string; temporal: string; backlog: number; packs: Pack[]};
const labels: Record<string,string> = {new:'Analysing', triaged:'Triaged', waiting_for_information:'Awaiting customer', ready:'Ready', drafting:'Preparing draft', drafted:'Draft ready', awaiting_review:'Needs your review', ready_to_execute:'Approved', executing:'Creating draft', verify_pending:'Verifying', completed:'Completed', blocked:'Needs attention', cancelled:'Cancelled', reconciliation_required:'Needs verification'};
const human = (s: string) => s.replace(/[._]/g, ' ').replace(/^./, c => c.toUpperCase());
const dateTime = (s: string) => new Date(s).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/v1' + path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Feya-Local':'1'},body:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Please check the entered information.');
  return value;
}
function Badge({phase}:{phase: string}) { return <span className={'badge ' + phase}><i/>{labels[phase] || human(phase)}</span>; }
function App() {
  const [workspace,setWorkspace] = useState<Workspace>();
  const [cases,setCases] = useState<Case[]>([]);
  const [selected,setSelected] = useState<string | null>(null);
  const [detail,setDetail] = useState<Detail>();
  const [view,setView] = useState('conversation');
  const [filter,setFilter] = useState('all');
  const [query,setQuery] = useState('');
  const [tab,setTab] = useState('overview');
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [newCase,setNewCase] = useState(false);
  const [notice,setNotice] = useState('');
  const [reason,setReason] = useState('');
  const [fault,setFault] = useState('none');
  const [manual,setManual] = useState(false);
  const caseOpener = useRef<HTMLElement | null>(null);
  const newCaseOpener = useRef<HTMLElement | null>(null);
  function openCase(id: string, opener = document.activeElement as HTMLElement | null) {
    caseOpener.current = opener;
    setSelected(id);
  }
  useEffect(() => {
    if (!selected) return;
    const previous = caseOpener.current;
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelected(null);
      if (e.key === 'Tab') {
        const nodes = [...document.querySelectorAll<HTMLElement>('.drawer button:not(:disabled), .drawer a, .drawer input, .drawer textarea, .drawer select, .drawer summary')];
        const first = nodes[0], last = nodes.at(-1);
        if (e.shiftKey && document.activeElement === first) {e.preventDefault();last?.focus();}
        if (!e.shiftKey && document.activeElement === last) {e.preventDefault();first?.focus();}
      }
    };
    document.addEventListener('keydown', key);
    return () => {document.removeEventListener('keydown', key);previous?.focus();};
  }, [selected]);
  const active = useRef(selected); active.current = selected;
  async function refresh() {
    const [ws,list] = await Promise.all([api<Workspace>('/workspace'),api<Case[]>('/cases')]);
    setWorkspace(ws); setCases(list);
    const id = active.current;
    if (id) {const data = await api<Detail>('/cases/' + id); if(active.current === id) setDetail(data);}
  }
  useEffect(() => {refresh().catch(e=>setError(e.message)); const timer=setInterval(()=>refresh().catch(e=>setError(e.message)),3000); return ()=>clearInterval(timer);},[]);
  useEffect(()=>{setDetail(undefined);setTab('overview');setReason('');setFault('none');setManual(false); if(selected) api<Detail>('/cases/'+selected).then(data=>{if(active.current===selected)setDetail(data);}).catch(e=>setError(e.message));},[selected]);
  async function perform(fn:()=>Promise<unknown>, message='') {setBusy(true);setError('');try{await fn();await refresh();setNotice(message);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const needsReview=cases.filter(c=>c.phase==='awaiting_review').length;
  const uncertain=cases.filter(c=>['reconciliation_required','blocked'].includes(c.phase)).length;
  const waiting=cases.filter(c=>c.phase==='waiting_for_information').length;
  const completed=cases.filter(c=>c.phase==='completed').length;
  const filtered=cases.filter(c => (view!=='approvals'||c.phase==='awaiting_review')&&(view!=='exceptions'||['blocked','reconciliation_required'].includes(c.phase))&&(filter==='all'||c.phase===filter)&&(c.subject+' '+c.customer_email).toLowerCase().includes(query.toLowerCase()));
  const pack=workspace?.packs.find(p=>p.id===detail?.pack_id);
  const action=detail?.actions.filter(a=>!['superseded','cancelled'].includes(a.status)).at(-1);
  const title = {conversation:'A conversation. A way forward.',today:'A little clarity for your day.',cases:'Every case. One clear view.',approvals:'Ready for your decision.',exceptions:'Let’s resolve the uncertainty.',packs:'Built around your business.',connections:'Your tools, working together.',agents:'Reasoning with clear boundaries.'}[view];
  function nav(id: string){setView(id);setFilter('all');setSelected(null);}
  async function decide(decision: string){if(!action)return; if(fault!=='none')await api('/demo/faults/'+action.id,{mode:fault});await api('/approvals/'+action.id+'/decide',{decision,expected_digest:action.digest,reason:reason || 'Reviewed the exact offer, customer, and source facts in the local workspace'});}
  return <div className="shell">
    <aside className="sidebar" inert={!!selected || newCase}>
      <a className="brand" href="/" aria-label="Feya home"><img className="brand-wordmark" src={feyaWordmark} alt="feya"/><span className="brand-caption">BUSINESS, IN GOOD HANDS.</span></a>
      <div className="workspace-switch"><span className="workspace-icon" aria-hidden="true">F</span><div><b>{workspace?.name || 'Feya'}</b><small>Local workspace</small></div><ChevronRight size={15}/></div>
      <span className="nav-label">WORKSPACE</span>
      <nav>{[{id:'conversation',label:'Conversation',icon:MessageSquare},{id:'today',label:'Today',icon:LayoutGrid},{id:'cases',label:'All cases',icon:Inbox},{id:'approvals',label:'Approvals',icon:ShieldCheck,count:needsReview},{id:'exceptions',label:'Needs attention',icon:TriangleAlert,count:uncertain}].map(n=><button key={n.id} className={view===n.id?'nav-item active':'nav-item'} onClick={()=>nav(n.id)}><n.icon size={18}/>{n.label}{!!n.count&&<span className="nav-count">{n.count}</span>}</button>)}</nav>
      <span className="nav-label second">YOUR OPERATIONS</span>
      <nav>{[{id:'packs',label:'Business packs',icon:Layers3},{id:'agents',label:'Agent suite',icon:Sparkles},{id:'connections',label:'Connections',icon:Link2}].map(n=><button key={n.id} className={view===n.id?'nav-item active':'nav-item'} onClick={()=>nav(n.id)}><n.icon size={18}/>{n.label}</button>)}</nav>
      <div className="sidebar-bottom"><div className="safe-note"><ShieldCheck size={20}/><b>Thoughtful by default.</b><p>Agents prepare. You decide.<br/>Every outcome is checked.</p></div><div className="user"><span className="avatar">Y</span><div><b>Your local workspace</b><small>Synthetic data only</small></div><Settings2 size={16}/></div></div>
    </aside>
    <main inert={!!selected || newCase}>
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={14}/> <b>{human(view==='exceptions'?'Needs attention':view)}</b></div><div className="topbar-right"><span className="local-pill"><i/>LOCAL DEMO</span><span className="avatar small">Y</span></div></header>
      {error&&<div className="alert error" role="alert"><TriangleAlert size={18}/>{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
      {notice&&<div className="alert success" role="status"><Check size={18}/>{notice}<button aria-label="Dismiss message" onClick={()=>setNotice('')}><X size={16}/></button></div>}
      <div className="page">
        <div className="page-heading"><div><div className="eyebrow">{view==='today'?new Date().toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'}):'FEYA WORKSPACE'}</div><h1>{title}</h1><p>{view==='conversation'?'Ask a question, delegate a task, or work through an idea.':'Keep work moving, with the context and control you need.'}</p></div>{view!=='conversation'&&<button className="primary" onClick={e=>{newCaseOpener.current=e.currentTarget;setNewCase(true);}}><Plus size={17}/>New enquiry</button>}</div>
        <div hidden={view!=='conversation'}><Conversation api={api} runner={workspace?.runner}/></div>
        {['today','cases','approvals','exceptions'].includes(view)&&<>
          <section className="metrics" aria-label="Case overview">{[{label:'Needs your review',value:needsReview,icon:ShieldCheck,phase:'awaiting_review',note:'Prepared and ready for a decision'},{label:'Awaiting customer',value:waiting,icon:Clock3,phase:'waiting_for_information',note:'Missing details, clearly tracked'},{label:'Needs verification',value:uncertain,icon:Activity,phase:'reconciliation_required',note:'Uncertain outcomes stay visible'},{label:'Completed',value:completed,icon:CheckCheck,phase:'completed',note:'Verified drafts or manual handling'}].map(m=><button className={'metric '+(filter===m.phase?'selected':'')} key={m.label} onClick={()=>setFilter(filter===m.phase?'all':m.phase)}><span>{m.label}<m.icon size={18}/></span><strong>{m.value.toString().padStart(2,'0')}</strong><small>{m.note}</small></button>)}</section>
          <div className="section-title"><div><h2>{view==='approvals'?'Approval queue':view==='exceptions'?'Attention queue':'Your work queue'}</h2><span className="count">{filtered.length}</span></div><span className="subtle"><span className={'status-dot '+(workspace?.temporal==='connected'?'':'offline')}/>{workspace?.temporal==='connected'?'Workflow engine connected':'Checking workflow engine'}{workspace && workspace.backlog>0 ? ` · ${workspace.backlog} queued` : ''}</span></div>
          <section className="queue"><div className="queue-tools"><div className="tabs"><button className={filter==='all'?'selected':''} onClick={()=>setFilter('all')}>All work</button><button className={filter==='awaiting_review'?'selected':''} onClick={()=>setFilter('awaiting_review')}>For review{needsReview>0&&<b>{needsReview}</b>}</button><button className={filter==='waiting_for_information'?'selected':''} onClick={()=>setFilter('waiting_for_information')}>Waiting</button><button className={filter==='completed'?'selected':''} onClick={()=>setFilter('completed')}>Completed</button></div><label className="search"><Search size={16}/><input aria-label="Search cases" placeholder="Search cases…" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
          <div className="table-scroll"><table><thead><tr><th>CASE / CUSTOMER</th><th>STATUS</th><th>NEXT ACTION</th><th>BUSINESS PACK</th><th aria-label="Open case"/></tr></thead><tbody>{filtered.map(c=><tr key={c.id} className={selected===c.id?'selected':''}><td><button className="case-link" onClick={()=>openCase(c.id)}><span className={'case-icon '+(c.pack_id==='consulting'?'purple':'')}><FileText size={18}/></span><span><b>{c.subject}</b><small>{c.customer_email}</small></span></button></td><td><Badge phase={c.phase}/></td><td className="next-cell"><span>{c.next_action}</span></td><td><span className="pack-chip">{workspace?.packs.find(p=>p.id===c.pack_id)?.name || human(c.pack_id)}</span></td><td><button className="icon-button" aria-label={'Open '+c.subject} onClick={()=>openCase(c.id)}><ArrowRight size={17}/></button></td></tr>)}</tbody></table></div>
          {!filtered.length&&<div className="empty"><Inbox size={30}/><h3>{cases.length?'You’re clear here.':'A clear workspace starts with one enquiry.'}</h3><p>{cases.length?'Try another filter to see the rest of your work.':'Create a synthetic enquiry and follow it from missing information to a verified offer.'}</p>{!cases.length&&<button className="primary" disabled={busy} onClick={()=>perform(async()=>{const c=await api<{case_id:string}>('/demo/generic_enquiry',{});openCase(c.case_id);},'Synthetic enquiry added. Analysis is queued.')}><Sparkles size={16}/>Try the example enquiry</button>}</div>}
          <div className="queue-footer"><span><ShieldCheck size={14}/>Customer sends and provider dispatch are disabled.</span><span>{cases.length} case{cases.length===1?'':'s'} in this workspace</span></div></section>
          <div className="below-queue"><div><span className="feature-icon"><Layers3 size={23}/></span><div><h3>Your business. Your way of working.</h3><p>Required facts, approved rates, and review rules live in reusable business packs.</p><button className="text-button" onClick={()=>nav('packs')}>Explore business packs <ArrowRight size={14}/></button></div></div><div className="quiet-fact"><CheckCheck size={18}/><p><b>“Done” has evidence behind it.</b><br/>Provider drafts are read back before completion.</p></div></div>
        </>}
        {view==='packs'&&<div className="pack-grid">{workspace?.packs.map(p=><article className="panel pack-panel" key={p.id}><div className="panel-icon"><Layers3 size={25}/></div><span className="overline">BUSINESS PACK · v{p.version}</span><h2>{p.name}</h2><p>{p.description}</p><h4>Required information</h4><ul className="plain-list">{p.required_facts.map(f=><li key={f.key}><Check size={15}/>{f.label}</li>)}</ul><h4>Approved rates</h4>{Object.entries(p.rates).map(([key,r])=><div className="rate" key={key}><span>{r.label}</span><b>€{r.unit_price}</b></div>)}<div className="pack-rule"><ShieldCheck size={16}/>Offer approval required. Dispatch disabled.</div><button className="secondary full" disabled={busy} onClick={()=>perform(async()=>{const c=await api<{case_id:string}>('/demo/'+p.id,{});openCase(c.case_id);},'Example enquiry added.')} >Try this pack <ArrowRight size={16}/></button></article>)}</div>}
        {view==='agents'&&<><div className="agent-banner"><Sparkles size={28}/><div><h2>Small, focused runs. Shared business rules.</h2><p>Reasoning is bounded and evidence-linked. Pricing, authorization, and verification are deterministic.</p></div><span className="badge ready">{workspace?.runner==='fixture'?'Offline demo':workspace?.runner}</span></div><div className="agent-grid">{[{name:'Triage',desc:'Extracts source-cited facts. Unknowns stay unknown.',tag:workspace?.model || 'Loading…'},{name:'Requirements',desc:'Checks the facts your business pack needs.',tag:'Deterministic validator'},{name:'Proposal',desc:'Builds a draft using approved rates and exact decimal calculations.',tag:'Pack rate service'},{name:'Verification',desc:'Reads the provider record and compares every approved field.',tag:'Independent gateway'}].map((a,i)=><article className="panel" key={a.name}><span className="agent-number">0{i+1}</span><h2>{a.name}</h2><p>{a.desc}</p><span className="pack-chip">{a.tag}</span></article>)}</div><article className="panel provider-info"><h2>Bring the model account that works for you.</h2><p>Choose an explicit runner in the local configuration. Authentication stays with the account owner. A quota or login failure never switches billing providers.</p><div className="provider-row"><b>ChatGPT / Codex</b><span>PydanticAI · openai-codex provider</span><span className="pack-chip">Subscription option</span></div><div className="provider-row"><b>Claude</b><span>Official Claude Code · tools disabled</span><span className="pack-chip">Subscription option</span></div><div className="provider-row"><b>Provider API</b><span>PydanticAI · explicit model and API key</span><span className="pack-chip">Separate API billing</span></div><small>Current runner: {workspace?.runner}. Configuration and account instructions are in the local README.</small></article></>}
        {view==='connections'&&<><div className="connection-note"><ShieldCheck size={22}/><div><b>A safe place to try the full workflow.</b><p>This workspace uses simulated providers. No customer mailbox, calendar, or accounting account is connected.</p></div></div><div className="connections">{[{name:'Email simulator',text:'Source enquiries and reply drafts',cap:'Read enquiries · create drafts',icon:Inbox},{name:'Accounting simulator',text:'Offers, approved amounts, exact read-back',cap:'Create undispatched drafts · verify · reconcile',icon:FileText},{name:'Temporal',text:'Durable case workflows and recovery',cap:workspace?.temporal==='connected'?'Connected to local server':'Server unavailable',icon:Activity}].map(c=><article className="panel connection" key={c.name}><span className="panel-icon"><c.icon size={24}/></span><div><h2>{c.name}</h2><p>{c.text}</p><small>{c.cap}</small></div><span className="badge ready">{c.name==='Temporal'?workspace?.temporal:'Simulated'}</span></article>)}</div></>}
        <footer className="page-footer"><span>FEYA <span>·</span> Work with clarity.</span><span><CircleHelp size={13}/>Local prototype · v0.1</span></footer>
      </div>
    </main>
    {selected&&<><div className="drawer-backdrop" onClick={()=>setSelected(null)}/><aside className="drawer" role="dialog" aria-modal="true" aria-label="Case detail"><div className="drawer-top"><span>CASE DETAILS <span className="mono">{selected.slice(-8)}</span></span><button autoFocus className="icon-button" aria-label="Close case detail" onClick={()=>setSelected(null)}><X size={20}/></button></div>{!detail?<div className="loading"><LoaderCircle className="spin"/>Loading case…</div>:<>
      <div className="detail-heading"><Badge phase={detail.phase}/><h2>{detail.subject}</h2><p>{detail.customer_email}</p><div className="detail-meta"><span><Layers3 size={14}/>{pack?.name}</span><span>{dateTime(detail.created_at)}</span></div></div>
      <div className="detail-tabs tabs">{['overview','sources','activity'].map(t=><button key={t} onClick={()=>setTab(t)} className={tab===t?'selected':''}>{human(t)}{t==='sources'&&<b>{detail.evidence.length}</b>}</button>)}</div>
      <div className="detail-body">
        {tab==='overview'&&<><div className="next-box"><ArrowRight size={19}/><div><span className="overline">NEXT STEP</span><p>{detail.next_action}</p></div></div>
          <section className="detail-section"><h3>What we know</h3><dl className="facts">{pack?.required_facts.map(f=><div key={f.key}><dt>{f.label}</dt><dd>{detail.facts[f.key]?<><Check size={14}/>{detail.facts[f.key].value}</>:<span className="missing">Still needed</span>}</dd></div>)}</dl></section>
          {action&&<section className="detail-section"><div className="detail-section-title"><h3>{action.capability==='email.draft.create'?'Prepared reply':'Proposed offer'}</h3><Badge phase={action.status}/></div>
            {action.capability==='email.draft.create'?<div className="email-preview"><div><b>To</b>{action.payload.to}</div><div><b>Subject</b>{action.payload.subject}</div><pre>{action.payload.body}</pre></div>:<div className="offer-preview"><div className="offer-header"><FileText size={23}/><span>OFFER DRAFT<small>Not dispatched</small></span><b>{action.payload.currency}</b></div><p>{action.payload.customer_email}</p><div className="offer-line"><span>{human(action.payload.service)}<small>{action.payload.quantity} × {action.payload.unit_price}</small></span><b>{action.payload.subtotal}</b></div><div className="offer-tax"><span>Tax</span><span>{action.payload.tax}</span></div><div className="offer-total"><span>Total</span><b>{action.payload.currency} {action.payload.total}</b></div><small>Approved rate version {action.payload.rate_version}</small></div>}
            <div className="policy-checks">{action.policy_reasons.map(r=><div key={r}><ShieldCheck size={14}/>{r}</div>)}</div>
            {action.status==='awaiting_approval'&&<div className="approval-controls"><label>Review note <span>(optional)</span><textarea rows={2} placeholder="What informed your decision?" value={reason} onChange={e=>setReason(e.target.value)}/></label><details className="fault-options"><summary>Try a simulated provider failure</summary><select aria-label="Provider failure simulation" value={fault} onChange={e=>setFault(e.target.value)}><option value="none">Normal provider response</option><option value="timeout_after">Create offer, then lose the response</option><option value="timeout_before">Timeout before provider commit</option><option value="mismatch">Provider changes the approved amount</option><option value="read_failure">Provider read-back unavailable</option></select></details><div className="button-row"><button className="primary" disabled={busy} onClick={()=>perform(()=>decide('approve'),'Exact draft approved. Provider creation is queued.')}><Check size={16}/>Approve draft</button><button className="secondary" disabled={busy} onClick={()=>perform(()=>decide('reject'),'Proposal rejected. No provider draft was created.')}>Reject</button></div><small>Approves this exact draft only. No email or offer will be sent.</small></div>}
            {['uncertain','executing'].includes(action.status)&&<button className="secondary full" disabled={busy} onClick={()=>perform(()=>api('/action-intents/'+action.id+'/reconcile',{}),'Provider recheck queued. No second write will be attempted.')}><Activity size={16}/>Recheck provider</button>}
            {action.status==='verified'&&<div className="verified-note"><CheckCheck size={18}/><span>Provider draft verified <small>{action.provider_ref?.slice(-12)}</small></span></div>}
          </section>}
          {detail.phase==='waiting_for_information'&&<button className="secondary full" disabled={busy} onClick={()=>perform(()=>api('/cases/'+detail.id+'/demo-reply',{}),'Synthetic customer reply added to this case.')}><Plus size={16}/>Simulate the customer’s reply</button>}
          {detail.phase==='blocked'&&<button className="secondary full" disabled={busy} onClick={()=>perform(()=>api('/cases/'+detail.id+'/retry',{}),'Analysis retry queued.')}><Sparkles size={16}/>Retry analysis</button>}
          <div className="manual-actions"><a className="text-button" href={'/v1/cases/'+detail.id+'/export'} download><ArrowDownToLine size={14}/>Export case</a>{!['completed','cancelled','executing','verify_pending','reconciliation_required'].includes(detail.phase)&&<button className="text-button" onClick={()=>setManual(!manual)}>Handle manually</button>}</div>
          {manual&&<div className="manual-form"><label>Handling reason<textarea value={reason} onChange={e=>setReason(e.target.value)} placeholder="Explain what was handled outside Feya."/></label><div className="button-row"><button className="secondary" disabled={busy||!reason.trim()} onClick={()=>perform(()=>api('/cases/'+detail.id+'/complete-manually',{expected_version:detail.version,reason}),'Case marked manually handled; provider status is unchanged.')}>Mark handled</button><button className="secondary danger" disabled={busy||!reason.trim()} onClick={()=>perform(()=>api('/cases/'+detail.id+'/cancel',{expected_version:detail.version,reason}),'Case cancelled. Pending approvals revoked.')}>Cancel case</button></div></div>}
        </>}
        {tab==='sources'&&<>{detail.evidence.map((e,i)=><article className="source" key={e.id}><div><span className="source-number">{i+1}</span><b>{e.content.subject}</b></div><small>{e.content.sender} · {dateTime(e.created_at)}</small><pre>{e.content.body}</pre><code>{e.id}</code><div className="source-footer"><ShieldCheck size={14}/>Immutable observation · simulated email</div></article>)}</>}
        {tab==='activity'&&<><h3 className="timeline-heading">A clear record of every step</h3><ol className="timeline">{[...detail.timeline].reverse().map(e=><li key={e.id}><span className="timeline-dot"/><div><b>{human(e.kind)}</b><small>{human(e.actor)} · {dateTime(e.created_at)}</small>{typeof e.detail.reason==='string'&&e.detail.reason&&<p>{e.detail.reason}</p>}</div></li>)}</ol>{detail.runs.map(r=><div className="run-note" key={r.id}><Sparkles size={16}/><div><b>{human(r.role)} · {r.status}</b><small>{r.model}{r.usage.input_tokens!=null?` · ${r.usage.input_tokens} in / ${r.usage.output_tokens} out`:''}</small></div></div>)}</>}
      </div></>}
    </aside></>}
    {newCase&&<NewCase packs={workspace?.packs||[]} close={()=>setNewCase(false)} create={data=>perform(async()=>{const result=await api<{case_id:string}>('/ingest',data);setNewCase(false);openCase(result.case_id, newCaseOpener.current);},'Enquiry recorded. Analysis is queued.')}/>}
  </div>;
}
function NewCase({packs,close,create}:{packs:Pack[];close:()=>void;create:(data:unknown)=>Promise<void>}){
  const [pack,setPack]=useState(packs[0]?.id||'generic_enquiry'); const [sender,setSender]=useState('');const [subject,setSubject]=useState('');const [body,setBody]=useState('');const [sending,setSending]=useState(false);
  const dialog=useRef<HTMLDialogElement>(null); useEffect(()=>{dialog.current?.showModal();},[]);
  return <dialog ref={dialog} className="new-dialog" onCancel={close} onClose={close}><form onSubmit={async e=>{e.preventDefault();setSending(true);try{await create({event_id:crypto.randomUUID(),thread_id:crypto.randomUUID(),pack_id:pack,sender,subject,body});}finally{setSending(false);}}}><div className="modal-heading"><div><span className="overline">LOCAL SYNTHETIC WORKSPACE</span><h2>A new enquiry</h2></div><button type="button" className="icon-button" aria-label="Close new enquiry" onClick={close}><X/></button></div><p>Create a case from a synthetic customer message.</p><label>Business pack<select value={pack} onChange={e=>setPack(e.target.value)}>{packs.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button className="text-button" type="button" onClick={()=>{const f=packs.find(p=>p.id===pack)?.fixture;if(f){setSender(f.sender);setSubject(f.subject);setBody(f.body);}}}><Sparkles size={14}/>Use the example message</button><label>Customer email<input required type="email" value={sender} onChange={e=>setSender(e.target.value)} placeholder="alex@example.test"/></label><label>Subject<input required maxLength={200} value={subject} onChange={e=>setSubject(e.target.value)}/></label><label>Message<textarea required rows={6} maxLength={16000} value={body} onChange={e=>setBody(e.target.value)}/></label><small>The offline demo extracts explicit key: value lines. A model runner can interpret natural-language enquiries.</small><div className="button-row end"><button type="button" className="secondary" onClick={close}>Cancel</button><button className="primary" disabled={sending}><Plus size={16}/>Create case</button></div></form></dialog>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
