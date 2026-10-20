// Shared helpers of the supplier scan pages (dashboard, new scan, results).
export const TIERS = {
  1: 'Tier 1 · Auto-confirm',
  2: 'Tier 2 · Steward review',
  3: 'Tier 3 · Functional split / hierarchy',
  4: 'Tier 4 · Watchlist'
}
export const TIER_BADGE = { 1: 'HIGH', 2: 'MEDIUM', 3: 'LOW', 4: 'LOW' }
export const DECISIONS = ['Confirmed as duplicate', 'Not a duplicate', 'Deferred']
export const RULES = {
  A01: 'Tax / registration anchor', A02: 'Cross-ref / EDI anchor', N01: 'Name', L01: 'Address / GLN',
  C01: 'Phone / email', C02: 'Contact person', B01: 'Operational booster', P01: 'Branch penalty'
}

export function formatScanTime(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export async function fetchJson(url, options) {
  const res = await fetch(url, options)
  const body = await res.json().catch(() => null)
  if (!res.ok || body?.success === false) throw new Error(body?.error || body?.detail?.[0]?.msg || `Request failed (${res.status}).`)
  return body
}

export async function downloadScanExcel(scanId) {
  const res = await fetch(`/api/spec-dedup/scans/${scanId}/export`)
  if (!res.ok) throw new Error(`Excel export failed (${res.status}).`)
  const url = URL.createObjectURL(await res.blob())
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || `Supplier Duplicates Scan ${scanId}.xlsx`
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}

// Entities that can be scanned. Each has its own pages under `base`.
export const SCAN_ENTITIES = {
  supplier: {
    label: 'Supplier', plural: 'Suppliers', base: '/supplier-scans', hasConditions: true,
    reports: ['SupplierInfoGeneral', 'CommMethod', 'SupplierInfoContact', 'SupplierInfoMsgSetup', 'SupplierInfoAddress', 'SupplierInfoAddressType',
      'IdentityPayInfo', 'Supplier (Purchasing)', 'IdentityInvoiceInfo', 'SrmSuppInfo'],
    reportHint: 'Select the 10 IFS Quick Report exports. Each report is recognised from its columns, not its file name; the general supplier report is required and any missing report is skipped.'
  },
  customer: {
    label: 'Customer', plural: 'Customers', base: '/customer-scans', hasConditions: false,
    reports: ['CUS01_General', 'CUS02_CustomerInfoAddresses', 'CUS03_AddressTypes', 'CUS08_CustomerInvoiceCompanies', 'CUS09_CustomerPayments', 'CUS11_CustOrdCustomers'],
    reportHint: 'Select the customer Quick Report exports (or the combined workbook exported from this tool). Reports are matched by their CUS code or their columns; the general customer report is required.'
  }
}
export const SOURCE_LABEL = { reports: 'Quick reports', ifs: 'IFS environment' }
