// In-memory result of the last fetch (cleared on page reload).
let current = null

export function setFetched(results) {
  current = { results, fetchedAt: new Date().toISOString() }
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
