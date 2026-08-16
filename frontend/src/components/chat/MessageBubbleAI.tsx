import { marked } from 'marked';
import { useMemo } from 'react';

interface Props {
  content: string;
  streaming?: boolean;
}

export function MessageBubbleAI({ content, streaming }: Props) {
  const html = useMemo(() => marked.parse(content || '', { async: false }) as string, [content]);

  return (
    <article className="msg-ai">
      <header className="msg-ai-head">
        <span className="msg-ai-mark">L</span>
        <span className="msg-label">LearnWise · The answer</span>
        <span className="msg-ai-rule" />
      </header>
      <div
        className={`msg-ai-body${streaming ? ' streaming' : ''}`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </article>
  );
}
