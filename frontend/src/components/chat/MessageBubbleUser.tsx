interface Props {
  content: string;
  index: number;
}

export function MessageBubbleUser({ content, index }: Props) {
  return (
    <div className="msg-user">
      <div className="msg-label">You · {String(index + 1).padStart(2, '0')}</div>
      <div className="bubble-user">{content}</div>
    </div>
  );
}
