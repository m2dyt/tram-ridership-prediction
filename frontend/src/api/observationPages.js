export async function fetchObservationPages(fetchPage, params) {
  return fetchPages(fetchPage, "/observations", params);
}

export async function fetchPages(fetchPage, path, params) {
  const items = [];
  const seen = new Set();
  let cursor;
  do {
    const page = await fetchPage(path, {
      ...params,
      limit: 1000,
      cursor,
    });
    items.push(...(page.items || []));
    if (!page.page?.has_more) break;
    cursor = page.page.next_cursor;
    if (!cursor || seen.has(cursor) || items.length > 1_000_000) {
      throw new Error(
        "Не удалось загрузить все страницы данных. Сузьте период и повторите запрос.",
      );
    }
    seen.add(cursor);
  } while (true);
  return items;
}
