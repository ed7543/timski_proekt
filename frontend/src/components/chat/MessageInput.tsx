import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react';
import type { KeyboardEvent } from 'react';
import { SendIcon } from '../icons';

interface Props {
  disabled: boolean;
  live: boolean;
  subject: string;
  onSend: (text: string) => void;
}

export interface MessageInputHandle {
  setValue: (text: string) => void;
  focus: () => void;
}

export const MessageInput = forwardRef<MessageInputHandle, Props>(function MessageInput(
  { disabled, live, subject, onSend },
  ref,
) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoresize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  };

  useEffect(() => {
    autoresize();
  }, [value]);

  useImperativeHandle(ref, () => ({
    setValue: (text: string) => setValue(text),
    focus: () => textareaRef.current?.focus(),
  }));

  const submit = (text?: string) => {
    const content = (text ?? value).trim();
    if (!content || disabled) return;
    setValue('');
    onSend(content);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className="composer-box">
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder="Ask anything — Shift + Enter for a new line"
            value={value}
            disabled={disabled}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="composer-foot">
            <div className="status">
              <span className={`pulse ${live ? '' : 'off'}`} />
              <span>{live ? 'Live docs search on' : 'Base knowledge only'}</span>
              <span className="div" />
              <span className="subject">{subject}</span>
            </div>
            <button
              className="send-btn"
              aria-label="Send"
              disabled={!value.trim() || disabled}
              onClick={() => submit()}
            >
              <SendIcon />
            </button>
          </div>
        </div>
        <p className="legal">LearnWise may surface inaccurate excerpts — verify with sources.</p>
      </div>
    </div>
  );
});
