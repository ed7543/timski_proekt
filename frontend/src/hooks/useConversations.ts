import { useCallback, useEffect, useRef, useState } from 'react';
import * as conversationsApi from '../api/conversations';
import type { ConversationOut } from '../types/conversation';
import { useAuth } from '../context/AuthContext';

export function useConversations() {
  const { status } = useAuth();
  const [threads, setThreads] = useState<ConversationOut[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (search?: string) => {
    if (status !== 'authenticated') {
      setThreads([]);
      return;
    }
    try {
      const data = await conversationsApi.listConversations(search || undefined);
      setThreads(data);
    } catch {
      /* leave previous list on transient failure */
    }
  }, [status]);

  useEffect(() => {
    load(searchQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const onSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      load(value.trim());
    }, 250);
  }, [load]);

  const remove = useCallback(async (id: number) => {
    try {
      await conversationsApi.deleteConversation(id);
    } catch {
      /* ignore - still remove locally for responsiveness */
    }
    setThreads((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const rename = useCallback(async (id: number, title: string) => {
    const updated = await conversationsApi.renameConversation(id, { title });
    setThreads((prev) => prev.map((t) => (t.id === id ? updated : t)));
    return updated;
  }, []);

  const upsertLocal = useCallback((conv: ConversationOut) => {
    setThreads((prev) => {
      const exists = prev.some((t) => t.id === conv.id);
      if (exists) return prev.map((t) => (t.id === conv.id ? conv : t));
      return [conv, ...prev];
    });
  }, []);

  return {
    threads,
    searchQuery,
    onSearchChange,
    reload: () => load(searchQuery),
    remove,
    rename,
    upsertLocal,
  };
}
