export async function fetchModelCatalog(fetchPage, params) {
  const page = await fetchPage("/models", params);
  return {
    items: page.items || [],
    activeVersionError: page.active_version_error || null,
  };
}
