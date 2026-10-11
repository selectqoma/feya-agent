import { useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowUp, Check, FileText, ListChecks, LoaderCircle, MessageSquare, Plus, X } from 'lucide-react';
import feyaMark from './feya.svg';
import feyaWordmark from './feya-wordmark.svg';
import './conversation.css';
import Markdown from './Markdown';

type Api = <T>(path: string, body?: unknown) => Promise<T>;
type Thread = {id: string; title: string};
type Message = {id: string; role: string; content: string; task_id?: string; created_at: string};
type Source = {id: string; title: string; content: string};
type Progress = {id: string; kind: string; content: string; created_at: string};
type CompletionChecks = {passed: boolean; label: string; checks: {name: string; passed: boolean; detail: string; blocking?: boolean}[]};
type Task = {sources?: Source[]; id: string; objective: string; deliverable: string; status: string; version: number; progress?: Progress[]; result_markdown?: string;
  acceptance_criteria?: string[]; candidate_markdown?: string; completion_checks?: Partial<CompletionChecks>; completion_label?: string;
  error_code?: string; failure_message?: string; calls_reserved?: number; tokens_reserved?: number; seconds_reserved?: number;
  unknown_usage_calls?: number; limits?: {calls: number; tokens: number; active_seconds: number; generation_calls: number}; next_attempt_at?: string; can_resume?: boolean};
type ThreadDetail = Thread & {messages: Message[]; sources: Source[]; tasks: Task[]; pending: number};
type TaskDetail = Task & {sources?: Source[]};
const label = (value: string) => value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const taskLabel = (task: Task) => task.completion_label === 'draft_prepared' && task.status === 'completed' ? 'Draft prepared' : label(task.status);
const activeTask = (task: Task) => ['queued', 'running', 'waiting_for_input'].includes(task.status);

export default function Conversation({api, runner}: {api: Api; runner?: string}) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<ThreadDetail>();
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sourceForm, setSourceForm] = useState(false);
  const [sourceTitle, setSourceTitle] = useState('');
  const [sourceContent, setSourceContent] = useState('');
  const [taskId, setTaskId] = useState('');
  const [taskDetail, setTaskDetail] = useState<TaskDetail>();
  const [instruction, setInstruction] = useState('');
  const current = useRef(selected); current.current = selected;
  const currentTask = useRef(taskId); currentTask.current = taskId;
  const request = useRef<{content: string; id: string} | undefined>(undefined);
  const drafts = useRef(new Map<string, {draft: string; sourceForm: boolean; sourceTitle: string; sourceContent: string; request: typeof request.current}>());
  const log = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const task = taskDetail || detail?.tasks.find(t => t.id === taskId);
  const sources = [...new Map([...(detail?.sources || []), ...(detail?.tasks.flatMap(t => t.sources || []) || []),
    ...(taskDetail?.sources || [])].map(source => [source.id, source])).values()];

  async function refresh() {
    const list = await api<Thread[]>('/conversations');
    setThreads(list);
    const id = current.current;
    if (id) {
      const data = await api<ThreadDetail>('/conversations/' + id);
      if (current.current === id) setDetail(data);
    }
    const idTask = currentTask.current;
    if (idTask) {
      const data = await api<TaskDetail>('/tasks/' + idTask);
      if (currentTask.current === idTask) setTaskDetail(data);
    }
  }

  useEffect(() => {
    let mounted = true;
    api<Thread[]>('/conversations').then(list => {
      if (!mounted) return;
      setThreads(list);
      if (list.length) setSelected(list[0].id);
    }).catch(e => {if (mounted) setError(e.message);}).finally(() => {if (mounted) setLoading(false);});
    const timer = setInterval(() => refresh().catch(e => {if (mounted) setError(e.message);}), 3000);
    return () => {mounted = false; clearInterval(timer);};
  }, []);

  useEffect(() => {
    setDetail(undefined); setTaskId(''); setTaskDetail(undefined); setInstruction('');
    follow.current = true;
    if (selected) api<ThreadDetail>('/conversations/' + selected)
      .then(data => {if (current.current === selected) setDetail(data);})
      .catch(e => setError(e.message));
  }, [selected]);

  useEffect(() => {
    if (follow.current && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [detail?.messages.length]);

  async function perform(work: () => Promise<void>) {
    setBusy(true); setError('');
    try {await work(); await refresh();}
    catch (e) {setError((e as Error).message);}
    finally {setBusy(false);}
  }

  async function ensureThread(title: string) {
    if (current.current) return current.current;
    const created = await api<Thread>('/conversations', {title: title.slice(0, 100)});
    drafts.current.delete('');
    current.current = created.id;
    setSelected(created.id);
    return created.id;
  }

  async function send() {
    const content = draft.trim();
    if (!content) return;
    await perform(async () => {
      const id = await ensureThread(content);
      if (request.current?.content !== content) request.current = {content, id: crypto.randomUUID()};
      await api('/conversations/' + id + '/messages', {content, request_id: request.current.id});
      request.current = undefined;
      setDraft(value => value.trim() === content ? '' : value); follow.current = true;
    });
  }

  function select(id: string) {
    if (id === current.current) return;
    drafts.current.set(current.current, {draft, sourceForm, sourceTitle, sourceContent, request: request.current});
    const saved = drafts.current.get(id);
    current.current = id; setSelected(id); setDraft(saved?.draft || ''); setError('');
    setSourceForm(saved?.sourceForm || false); setSourceTitle(saved?.sourceTitle || '');
    setSourceContent(saved?.sourceContent || ''); request.current = saved?.request;
  }

  async function taskAction(action: string) {
    if (!task) return;
    await perform(async () => {
      const updated = await api<TaskDetail>('/tasks/' + task.id + '/' + action, {
        expected_version: task.version,
        instruction: instruction.trim() || (action === 'cancel' ? 'Cancelled by the operator.' : ''),
      });
      setTaskDetail(updated); setInstruction('');
    });
  }

  return <section className="conversation-workspace" aria-label="Conversation workspace">
    <div className="conversation-toolbar">
      <label><MessageSquare size={16}/><span className="sr-only">Choose conversation</span><select value={selected} disabled={busy || loading} onChange={e => select(e.target.value)}>
        <option value="">New conversation</option>
        {threads.map(t => <option value={t.id} key={t.id}>{t.title}</option>)}
      </select></label>
      <button className="secondary" disabled={busy} onClick={() => select('')}><Plus size={15}/>New conversation</button>
    </div>
    {error && <div className="alert error" role="alert">{error}<button aria-label="Dismiss conversation error" onClick={() => setError('')}><X size={16}/></button></div>}
    <div className="conversation-columns">
      <div className="conversation-main">
        <div className="conversation-log" role="log" aria-label="Messages" aria-live="polite" aria-relevant="additions" ref={log} onScroll={() => {
          const el = log.current;
          if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}>
          {loading || (selected && !detail) ? <div className="loading"><LoaderCircle size={20} className="spin"/>Loading conversation…</div>
            : !detail?.messages.length ? <div className="conversation-welcome"><img src={feyaWordmark} alt="feya"/><span className="overline">YOUR COMPANY ASSISTANT</span><h2>What shall we work on?</h2><p>Think something through together, or hand over a task. Feya keeps track while you carry on.</p><div className="conversation-starters">{['Help me plan a customer onboarding process.', 'Compare the suppliers in my notes and recommend one.', 'Turn my meeting notes into a follow-up draft.'].map(text => <button key={text} onClick={() => setDraft(text)}>{text}<ArrowUp size={14}/></button>)}</div></div>
              : detail.messages.map(m => <article key={m.id} className={'conversation-message role-' + m.role}><div className="message-author">{m.role === 'assistant' ? <img src={feyaMark} alt=""/> : null}<b>{m.role === 'user' ? 'You' : m.role === 'assistant' ? 'Feya' : 'Task update'}</b><time dateTime={m.created_at}>{new Date(m.created_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</time></div>{m.role === 'assistant' ? <Markdown text={m.content} sources={sources}/> : <div className="message-content">{m.content}</div>}{m.task_id && <button className="text-button" onClick={() => {setTaskId(m.task_id!); setTaskDetail(undefined); setInstruction('');}}>View task <ListChecks size={14}/></button>}</article>)}
        </div>
        <div className="conversation-compose-area">
          {!!detail?.pending && <p className="conversation-pending" role="status"><LoaderCircle size={13} className="spin"/>Feya is working on your message. You can keep chatting.</p>}
          {sourceForm && <form className="conversation-source-form" onSubmit={e => {e.preventDefault(); void perform(async () => {
            const id = await ensureThread(sourceTitle.trim());
            await api('/conversations/' + id + '/sources', {title: sourceTitle.trim(), content: sourceContent.trim()});
            setSourceTitle(''); setSourceContent(''); setSourceForm(false);
          });}}><div className="section-title"><h3>Add source material</h3><button type="button" aria-label="Close source form" onClick={() => setSourceForm(false)}><X size={16}/></button></div><label>Source title<input required maxLength={160} value={sourceTitle} onChange={e => setSourceTitle(e.target.value)}/></label><label>Paste notes or document text<textarea aria-describedby="source-limits" required rows={5} maxLength={12000} value={sourceContent} onChange={e => setSourceContent(e.target.value)}/></label><p className="conversation-hint" id="source-limits">Up to 8 sources per conversation, with 14,000 UTF-8 bytes of source content in total. Each source can contain up to 12,000 characters.</p><button className="secondary" disabled={busy || !sourceTitle.trim() || !sourceContent.trim()}><Check size={15}/>Add source</button></form>}
          <form className="conversation-composer" onSubmit={e => {e.preventDefault(); void send();}}>
            <label className="sr-only" htmlFor="conversation-message">Message Feya</label>
            <textarea id="conversation-message" placeholder="Ask Feya, or delegate a task…" value={draft} maxLength={8000} rows={3} onChange={e => setDraft(e.target.value)}/>
            <div><button type="button" className="text-button" onClick={() => setSourceForm(!sourceForm)} aria-expanded={sourceForm}><Plus size={15}/>Add source</button><button className="primary" disabled={busy || !draft.trim()}>{busy ? <LoaderCircle size={16} className="spin"/> : <ArrowUp size={16}/>}Send</button></div>
          </form>
          <p className="conversation-hint">{runner === 'fixture' ? 'Offline demo responses. Configure a model account for live conversation.' : 'Works with the material you provide. No web browsing or external actions in this conversation.'}</p>
        </div>
      </div>
      <aside className="conversation-context" aria-label="Conversation tasks and sources">
        <div className="section-title"><h2><ListChecks size={17}/>Delegated work</h2><span className="count">{detail?.tasks.length || 0}</span></div>
        {!detail?.tasks.length && <p className="context-empty">Give Feya a task in the conversation. Progress and results will appear here.</p>}
        {detail?.tasks.map(t => <button key={t.id} className={'conversation-task ' + (t.id === taskId ? 'selected' : '')} onClick={() => {setTaskId(t.id); setTaskDetail(undefined); setInstruction('');}}><span className={'badge task-' + t.status}>{['running', 'queued'].includes(t.status) ? <LoaderCircle size={11} className="spin"/> : <i/>}{taskLabel(t)}</span><b>{t.objective}</b>{t.progress?.length ? <small>{t.progress.at(-1)?.content}</small> : null}</button>)}
        {task && <section className="conversation-task-detail" aria-label="Selected task"><div className="section-title"><h3>Task details</h3><button aria-label="Close task details" onClick={() => {setTaskId(''); setTaskDetail(undefined);}}><X size={16}/></button></div><p>{task.deliverable}</p>{task.progress?.length ? <ul className="task-progress">{task.progress.map(step => <li key={step.id}><b>{label(step.kind)}</b><span>{step.content}</span></li>)}</ul> : null}

          {!!task.acceptance_criteria?.length && <details open><summary>Acceptance criteria</summary><ol>{task.acceptance_criteria.map((criterion, i) => <li key={i}>{criterion}</li>)}</ol></details>}
          {task.failure_message && <div className="task-failure" role="status"><b>{label(task.error_code || 'Task needs attention')}</b><p>{task.failure_message}</p>{task.next_attempt_at && <small>Next retry: {new Date(task.next_attempt_at).toLocaleTimeString()}</small>}</div>}
          {task.limits && <details className="task-budget"><summary>Work budget · {task.calls_reserved ?? 0}/{task.limits.calls} requests</summary><p>Across all attempts, reviews and resumptions.</p><dl><dt>Reserved tokens</dt><dd>{(task.tokens_reserved ?? 0).toLocaleString()} / {task.limits.tokens.toLocaleString()}</dd><dt>Reserved execution time</dt><dd>{task.seconds_reserved ?? 0} / {task.limits.active_seconds} seconds</dd></dl><p>Reservations include interrupted calls. {task.unknown_usage_calls ?? 0} calls have unconfirmed usage. Subscription allowance is not available here.</p></details>}
          {!!task.completion_checks?.checks?.length && <details className="task-checks" open={task.completion_checks.passed === false}><summary>{task.completion_checks.passed ? 'Draft review complete' : 'Draft needs revision'}</summary><ul>{task.completion_checks.checks.map((check, i) => <li key={i}><b>{check.passed ? 'Passed' : check.blocking === false ? 'Review note' : 'Needs attention'} · {label(check.name)}</b><span>{check.detail}</span></li>)}</ul><p>Includes a separate model review and code checks. These do not certify factual accuracy or an external outcome.</p></details>}
          {task.completion_label === 'legacy_unreviewed' && <p>This result predates completion checks and has not been reviewed by the new checker.</p>}
          {task.status !== 'completed' && task.candidate_markdown && <details><summary>Read unapproved draft</summary><Markdown text={task.candidate_markdown} sources={sources}/></details>}
          {task.status === 'completed' && task.completion_label === 'draft_prepared' && <p>Draft prepared. Review the findings before use; no external action was performed.</p>}

          {task.status === 'completed' && <><a className="text-button" href={'/v1/tasks/' + task.id + '/artifact'} download><ArrowDownToLine size={14}/>Download result</a>{task.result_markdown && <details><summary>Read result</summary><Markdown text={task.result_markdown} sources={sources}/></details>}</>}
          {task.status === 'cancelled' && <p>This task was cancelled. Start a new task in the conversation to continue the work.</p>}
          {!['completed', 'cancelled'].includes(task.status) && <><label htmlFor="task-instruction">{task.status === 'waiting_for_input' ? 'Provide the missing information' : 'Additional instructions'}<textarea id="task-instruction" rows={3} value={instruction} maxLength={4000} onChange={e => setInstruction(e.target.value)} placeholder="Adjust the brief or add context…"/></label><div className="task-controls">{activeTask(task) && <button className="secondary" disabled={busy || !instruction.trim()} onClick={() => void taskAction('steer')}>Update task</button>}{['failed', 'waiting_for_input'].includes(task.status) && <button className="secondary" disabled={busy || task.can_resume === false} onClick={() => void taskAction('resume')}>Resume</button>}{activeTask(task) && <button className="text-button danger" disabled={busy} onClick={() => void taskAction('cancel')}>Cancel task</button>}</div></>}
        </section>}
        <div className="section-title source-heading"><h2><FileText size={17}/>Source material</h2><span className="count">{sources.length}</span></div>
        {!sources.length && <p className="context-empty">Add the notes and documents Feya should use for this conversation.</p>}
        {sources.map(s => <details className="conversation-source" id={'source-' + s.id} key={s.id}><summary>{s.title}</summary><small>{s.id}</small><div>{s.content}</div></details>)}
      </aside>
    </div>
  </section>;
}
