import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Source = {id: string; title: string};
type Node = {type: string; value?: string; url?: string; children?: Node[]};

export default function Markdown({text, sources}: {text: string; sources: Source[]}) {
  const byId = new Map(sources.map(source => [source.id, source]));
  function citations() {
    function walk(node: Node) {
      if (!node.children || ['link', 'linkReference', 'code', 'inlineCode', 'html'].includes(node.type)) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) {walk(child); return [child];}
        const parts: Node[] = [];
        let offset = 0;
        for (const match of child.value.matchAll(/\[([a-zA-Z0-9_.:-]+)\]/g)) {
          const source = byId.get(match[1]);
          if (!source) continue;
          parts.push({type: 'text', value: child.value.slice(offset, match.index)});
          parts.push({type: 'link', url: '#source-' + source.id,
            children: [{type: 'text', value: source.title}]});
          offset = match.index! + match[0].length;
        }
        parts.push({type: 'text', value: child.value.slice(offset)});
        return parts;
      });
    }
    return walk;
  }
  return <div className="message-content markdown-content"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm, citations]} components={{
    a: ({href, children}) => {
      const source = href?.startsWith('#source-') ? byId.get(href.slice(8)) : undefined;
      if (source) return <a className="source-citation" href={href} title={'View source: ' + source.title} onClick={event => {
        const target = document.getElementById('source-' + source.id);
        if (target instanceof HTMLDetailsElement) {
          event.preventDefault(); target.open = true;
          target.querySelector('summary')?.focus(); target.scrollIntoView({block: 'nearest'});
        }
      }}>{children}</a>;
      return href && /^(https?:\/\/|mailto:)/i.test(href)
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
    },
    img: ({alt}) => <span className="markdown-image-note">[Image: {alt || 'not displayed'}]</span>,
    table: ({children}) => <div className="markdown-table" role="region" aria-label="Report table" tabIndex={0}><table>{children}</table></div>,
  }}>{text}</ReactMarkdown></div>;
}
