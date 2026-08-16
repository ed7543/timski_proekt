export function MessageBubbleError({ content }: { content: string }) {
  return (
    <article className="msg-ai">
      <header className="msg-ai-head">
        <span className="msg-ai-mark">L</span>
        <span className="msg-label">LearnWise · Error</span>
        <span className="msg-ai-rule" />
      </header>
      <div className="msg-error">{content}</div>
    </article>
  );
}
