/** Mirrors `extract_merchant_from_narration` in `transaction_import.py` for table display. */

const UPI_PAYEE_AFTER_REF = /UPI\/(?:DR|CR)\/\d{6,22}\/\s*([^/]+)/i
const UPI_PAYEE_NO_REF = /UPI\/(?:DR|CR)\/([^/]+)\//i

function cleanSegment(s: string): string {
  return s.replace(/\s+/g, ' ').trim()
}

export function merchantLabelForDisplay(raw: string | null | undefined): string {
  if (raw == null || !String(raw).trim()) {
    return ''
  }
  const t = String(raw).trim()
  const m1 = t.match(UPI_PAYEE_AFTER_REF)
  if (m1?.[1]) {
    return cleanSegment(m1[1]).slice(0, 200)
  }
  const m2 = t.match(UPI_PAYEE_NO_REF)
  if (m2?.[1] && !/^\d+$/.test(m2[1].trim())) {
    return cleanSegment(m2[1]).slice(0, 200)
  }
  if (!t.includes('/') && t.length <= 64) {
    return t.slice(0, 200)
  }
  return t.slice(0, 200)
}

export function formatMerchantCell(raw: string | null | undefined): string {
  const s = merchantLabelForDisplay(raw)
  return s || '—'
}
