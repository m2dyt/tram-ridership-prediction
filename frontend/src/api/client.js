export class ApiError extends Error {
  constructor(message, status, code, requestId) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export function createClient(token, fetcher = fetch) {
  async function request(
    path,
    { query = {}, body, signal, idempotencyKey } = {},
  ) {
    const params = new URLSearchParams(
      Object.entries(query).filter(
        ([, v]) => v !== undefined && v !== null && v !== "",
      ),
    );
    const response = await fetcher(
      `/api/v1${path}${params.size ? "?" + params : ""}`,
      {
        method: body === undefined ? "GET" : "POST",
        signal,
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      },
    );
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new ApiError(
        data?.message || `HTTP ${response.status}`,
        response.status,
        data?.code,
        data?.request_id,
      );
    return data;
  }
  async function all(path, query = {}, signal, collection = "items") {
    const items = [];
    let cursor;
    const seen = new Set();
    do {
      const page = await request(path, {
        query: { ...query, limit: 1000, cursor },
        signal,
      });
      items.push(...page[collection]);
      cursor = page.page?.has_more ? page.page.next_cursor : null;
      if (cursor && (seen.has(cursor) || items.length > 1_000_000))
        throw new Error(
          "Слишком большой или некорректный ответ. Сузьте выборку.",
        );
      seen.add(cursor);
    } while (cursor);
    return items;
  }
  return { request, all };
}
