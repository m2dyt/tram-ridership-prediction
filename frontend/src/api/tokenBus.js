let memoryToken = localStorage.getItem("tram_operator_token") || null;
const listeners = new Set();

export function updateToken(token) {
  memoryToken = token;
  if (token) {
    localStorage.setItem("tram_operator_token", token);
  } else {
    localStorage.removeItem("tram_operator_token");
  }
  listeners.forEach((l) => l(token));
}

export function getToken() {
  return memoryToken;
}

export function subscribeToken(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
