import { useEffect, useRef } from 'react';
import { getConversation, getConversationStatus } from '../api/conversations';
import type { ConversationDetailOut } from '../types/conversation';

const IDLE_POLL_INTERVAL_MS = 2500;
// While someone's reply is actively generating, poll faster so the other
// members' "lag" before they see the finished reply is shorter - this is a
// cheap mitigation for the fact that only the sender's own tab gets true
// token-by-token streaming (see the group-chat plan's Context section for
// why full pub/sub broadcast isn't worth building for a 3-person cap).
const GENERATING_POLL_INTERVAL_MS = 1000;

/** Group-chat "real-time" strategy for up to 3 members: short-interval
 * polling rather than a pub/sub broadcast (see the group-chat plan's
 * Context section for why - a permanent design at this scale, not a
 * stepping stone). Only polls while the tab is visible and this tab isn't
 * itself mid-stream (so a poll never clobbers your own in-flight partial
 * reply - see ChatPage's isStreaming guard).
 *
 * Each tick hits the cheap GET /{id}/status (a message count + the
 * generating flag) rather than the full conversation - the full detail is
 * only fetched (via onUpdate) when the count actually changed, so an idle
 * conversation with a long history isn't re-transferred every tick just to
 * discover nothing happened. */
export function useConversationPolling(
  conversationId: number | null,
  isStreaming: boolean,
  currentMessageCount: number,
  onUpdate: (detail: ConversationDetailOut) => void,
) {
  const currentCountRef = useRef(currentMessageCount);
  currentCountRef.current = currentMessageCount;

  useEffect(() => {
    if (conversationId == null || isStreaming) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const scheduleNext = (delayMs: number) => {
      if (cancelled) return;
      timer = setTimeout(poll, delayMs);
    };

    const poll = async () => {
      if (cancelled) return;
      if (document.visibilityState !== 'visible') {
        scheduleNext(IDLE_POLL_INTERVAL_MS);
        return;
      }
      try {
        const status = await getConversationStatus(conversationId);
        if (cancelled) return;
        if (status.message_count !== currentCountRef.current) {
          const detail = await getConversation(conversationId);
          if (!cancelled) onUpdate(detail);
        }
        scheduleNext(status.generating ? GENERATING_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS);
      } catch {
        // Transient failure (offline, momentary 401 during token refresh, etc.) - just retry next tick.
        scheduleNext(IDLE_POLL_INTERVAL_MS);
      }
    };

    scheduleNext(IDLE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [conversationId, isStreaming, onUpdate]);
}
