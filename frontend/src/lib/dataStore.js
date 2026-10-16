// In-memory result of the last fetch (cleared on page reload).
let current = null

// Supplier and customer are fetched separately; each fetch replaces only its own entity.
export function setFetched(results) {
  const kept = (current?.results || []).filter((r) => !results.some((n) => n.entity === r.entity))
  current = { results: [...kept, ...results], fetchedAt: new Date().toISOString() }
}

export function getFetched() {
  return current
}

export function summarize(fetched) {
  const out = { fetchedAt: fetched?.fetchedAt || null, entities: {}, related: 0 }
  for (const r of fetched?.results || []) {
    for (const [stage, s] of Object.entries(r.stages)) {
      if (stage === 'general') out.entities[r.entity] = s.records.length
      else out.related += s.records.length
    }
  }
  return out
}
