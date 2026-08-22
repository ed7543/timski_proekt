import { useCallback, useRef, useState } from 'react';
import { getToken, setToken } from '../api/tokenStore';
import type { ChatMessage, ChatSource } from '../types/chat';

export interface DisplayMessage {
  id: string;
  role: 'user' | 'ai' | 'error';
  content: string;
  streaming?: boolean;
  /** Set when a stream ended with an error - shown alongside any partial
   * content already rendered, rather than replacing it (see ChatPage). */
  error?: string;
}

const uid = () => Math.random().toString(36).slice(2, 10);

interface StreamCallbacks {
  onConversationInfo?: (info: { id: number; title: string }) => void;
  onSources?: (sources: ChatSource[]) => void;
  onSessionExpired?: () => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

/**
 * SSE state machine for POST /api/chat. Native EventSource can't send custom
 * headers, so we need fetch() + a manual reader/decoder loop, splitting on
 * newlines and handling `event: conversation` / `event: sources` / `data: ...`
 * framing exactly like the original vanilla-JS app did.
 */
export function useChatStream() {
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (
      payloadMessages: ChatMessage[],
      opts: { subject: string | null; search: boolean; conversationId: number | null; courseId?: number | null },
      callbacks: StreamCallbacks,
      onChunk: (fullText: string) => void,
    ) => {
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      let fullText = '';

      try {
        const token = getToken();
        const resp = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            messages: payloadMessages,
            subject: opts.subject,
            search: opts.search,
            conversation_id: opts.conversationId,
            course_id: opts.courseId ?? null,
          }),
          signal: controller.signal,
        });

        if (resp.status === 401) {
          setToken(null);
          callbacks.onSessionExpired?.();
          return;
        }

        if (!resp.ok || !resp.body) {
          let detail = 'Something went wrong';
          try {
            const err = await resp.json();
            detail = err.detail || detail;
          } catch {
            /* ignore */
          }
          throw new Error(detail);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let expectSources = false;
        let expectConversation = false;
        let expectError = false;
        let doneReceived = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (line === 'event: conversation') {
              expectConversation = true;
              continue;
            }
            if (line === 'event: sources') {
              expectSources = true;
              continue;
            }
            if (line === 'event: error') {
              expectError = true;
              continue;
            }

            if (line.startsWith('data: ')) {
              const data = line.slice(6);

              if (expectConversation) {
                expectConversation = false;
                try {
                  const convInfo = JSON.parse(data);
                  if (convInfo?.id) {
                    callbacks.onConversationInfo?.(convInfo);
                  }
                } catch {
                  /* ignore malformed frame */
                }
                continue;
              }

              if (expectSources) {
                expectSources = false;
                try {
                  const sources = JSON.parse(data);
                  if (Array.isArray(sources)) {
                    callbacks.onSources?.(sources);
                    continue;
                  }
                } catch {
                  /* ignore malformed frame */
                }
              }

              if (expectError) {
                expectError = false;
                try {
                  const errPayload = JSON.parse(data);
                  callbacks.onError?.(errPayload?.message || 'The AI tutor had trouble responding.');
                } catch {
                  callbacks.onError?.('The AI tutor had trouble responding.');
                }
                continue;
              }

              if (data === '[DONE]') {
                doneReceived = true;
                callbacks.onDone?.();
                continue;
              }

              try {
                const chunk = JSON.parse(data);
                fullText += chunk;
                onChunk(fullText);
              } catch {
                /* ignore malformed frame */
              }
            }
          }
        }

        // The connection closed without a [DONE] sentinel and without throwing
        // (e.g. the server process died or a proxy cut the connection mid-stream)
        // - without this, the message would be left showing the "typing" state
        // forever with no explanation.
        if (!doneReceived) {
          callbacks.onError?.('Connection to the tutor was lost - the answer above may be incomplete.');
          callbacks.onDone?.();
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // User clicked "stop" - not a failure, just end cleanly and keep
          // whatever text streamed in so far.
          callbacks.onDone?.();
          return;
        }
        throw err;
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { send, isStreaming, abort };
}

export { uid };
