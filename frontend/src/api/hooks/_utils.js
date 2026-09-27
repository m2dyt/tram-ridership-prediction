import { apiFetch } from "../apiFetch";

export async function fetchJson(path, params = {}) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.append(key, value);
    }
  }
  const url = Array.from(searchParams.keys()).length > 0 ? `${path}?${searchParams.toString()}` : path;
  const res = await apiFetch(url);
  return res.json();
}
