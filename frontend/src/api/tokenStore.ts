const TOKEN_KEY = 'lw_token';

type Listener = (token: string | null) => void;

let listeners: Listener[] = [];

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
  listeners.forEach((l) => l(token));
}

export function onTokenChange(listener: Listener): () => void {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}
