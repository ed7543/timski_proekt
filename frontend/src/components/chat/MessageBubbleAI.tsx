import { useMemo } from 'react';
import { renderMarkdown } from '../../utils/markdown';

interface Props {
  content: string;
  streaming?: boolean;
  error?: string;
}

export function MessageBubbleAI({ content, streaming, error }: Props) {
  const html = useMemo(() => renderMarkdown(content), [content]);

  return (
    <article className="msg-ai">
      <header className="msg-ai-head">
        <span className="msg-ai-mark">L</span>
        <span className="msg-label">LearnWise · The answer</span>
        <span className="msg-ai-rule" />
      </header>
      {content && (
        <div
          className={`msg-ai-body${streaming ? ' streaming' : ''}`}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
      {error && <div className="msg-error">{error}</div>}
    </article>
  );
}
