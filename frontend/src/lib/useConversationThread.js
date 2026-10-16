import { useCallback, useEffect, useRef, useState } from 'react';

const validThread = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,200}$/.test(value);
const storageKey = owner => `metadiet:conversation:${owner}`;
const defaultThread = () => `chat_${new Date().toISOString().split('T')[0]}`;

function restoreThread(owner) {
  try {
    const stored = owner && sessionStorage.getItem(storageKey(owner));
    if (validThread(stored)) return stored;
  } catch (_error) { /* Storage may be blocked by the browser. */ }
  return defaultThread();
}

// Only an opaque thread pointer, never tokens, chat text or nutrition data.
export function useConversationThread(userId) {
  const owner = userId || null;
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const [state, setState] = useState(() => ({ owner, id: restoreThread(owner) }));
  useEffect(() => {
    setState(previous => previous.owner === owner ? previous : { owner, id: restoreThread(owner) });
  }, [owner]);
  useEffect(() => {
    if (owner && state.owner === owner) {
      try { sessionStorage.setItem(storageKey(owner), state.id); }
      catch (_error) { /* Blocked storage does not prevent the current conversation. */ }
    }
  }, [owner, state.owner, state.id]);

  const setThreadId = useCallback(id => {
    if (ownerRef.current !== owner || !validThread(id)) return;
    try {
      if (owner) sessionStorage.setItem(storageKey(owner), id);
    } catch (_error) { /* Keep the current tab usable without persistent storage. */ }
    setState({ owner, id });
  }, [owner]);

  return [state.id, setThreadId, state.owner === owner];
}
