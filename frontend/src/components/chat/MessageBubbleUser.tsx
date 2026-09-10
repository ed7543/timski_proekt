interface Props {
  content: string;
  index: number;
  /** Another member's display name in a group conversation - omitted (shows "You") for the viewer's own messages. */
  authorName?: string;
}

export function MessageBubbleUser({ content, index, authorName }: Props) {
  return (
    <div className="msg-user">
      <div className="msg-label">{authorName || 'You'} · {String(index + 1).padStart(2, '0')}</div>
      <div className="bubble-user">{content}</div>
    </div>
  );
}
