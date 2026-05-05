/**
 * Illustrative India individual income-tax estimates (resident).
 * Uses simplified slabs and standard deductions — not tax advice.
 */

const CESS = 1.04

function progressiveTax(taxableRupees: number, bands: { upto: number; rate: number }[]): number {
  let tax = 0
  let prev = 0
  for (const b of bands) {
    if (taxableRupees <= prev) {
      break
    }
    const slice = Math.min(taxableRupees, b.upto) - prev
    if (slice > 0) {
      tax += slice * b.rate
    }
    prev = b.upto
  }
  return tax * CESS
}

/** Old regime slabs on taxable income (approx., excluding surcharge). */
function taxOldOnTaxable(ti: number): number {
  const bands = [
    { upto: 250_000, rate: 0 },
    { upto: 500_000, rate: 0.05 },
    { upto: 1_000_000, rate: 0.2 },
    { upto: Number.POSITIVE_INFINITY, rate: 0.3 },
  ]
  return progressiveTax(Math.max(0, ti), bands)
}

/** New regime FY 2024–25 style slabs on taxable income (approx.). */
function taxNewOnTaxable(ti: number): number {
  const bands = [
    { upto: 300_000, rate: 0 },
    { upto: 700_000, rate: 0.05 },
    { upto: 1_000_000, rate: 0.1 },
    { upto: 1_200_000, rate: 0.15 },
    { upto: 1_500_000, rate: 0.2 },
    { upto: Number.POSITIVE_INFINITY, rate: 0.3 },
  ]
  return progressiveTax(Math.max(0, ti), bands)
}

export type TaxEstimateInputs = {
  /** Annual gross from income streams (paise). */
  annualGrossPaise: number
  /** Section 80C declared (paise), capped at ₹1.5L in model. */
  tax80cPaise: number
  /** Section 80D declared (paise), capped at ₹25k in model (illustrative). */
  tax80dPaise: number
}

/** Old regime: standard deduction ₹50k + 80C + 80D (capped). */
export function estimateOldRegimeTaxPaise(i: TaxEstimateInputs): number {
  const gross = i.annualGrossPaise / 100
  const std = 50_000
  const c80 = Math.min(i.tax80cPaise / 100, 150_000)
  const d80 = Math.min(i.tax80dPaise / 100, 25_000)
  const taxable = Math.max(0, gross - std - c80 - d80)
  return Math.round(taxOldOnTaxable(taxable) * 100)
}

/** New regime: standard deduction ₹75k (simplified; salary-style). */
export function estimateNewRegimeTaxPaise(i: TaxEstimateInputs): number {
  const gross = i.annualGrossPaise / 100
  const std = 75_000
  const taxable = Math.max(0, gross - std)
  return Math.round(taxNewOnTaxable(taxable) * 100)
}
