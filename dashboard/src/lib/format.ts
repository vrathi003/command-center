/** Money is stored as paise (integer); display as INR. */

export function formatPaise(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(rupees)
}

export function formatPaiseCompact(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    notation: rupees >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: rupees >= 100000 ? 1 : 2,
  }).format(rupees)
}
