let memoryToken = null;
const listeners = new Set();

export function updateToken(token) {
  memoryToken = token;
  listeners.forEach((l) => l(token));
}

export function getToken() {
  return memoryToken;
}

export function subscribeToken(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
