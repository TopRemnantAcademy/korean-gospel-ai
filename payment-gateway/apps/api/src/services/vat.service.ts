/**
 * VAT Calculation Service (Korean Tax Law compliant)
 * 
 * Rules:
 * 1. amountTotal is KRW integer (no decimal points).
 * 2. Floating-point numbers must NOT be returned for final values to avoid rounding discrepancies in accounting.
 * 3. amountSupply + amountVat == amountTotal must always be guaranteed.
 * 4. supply = round(total / 11 * 10)
 * 5. vat = total - supply
 */
export interface TaxBreakdown {
  amountSupply: number;
  amountVat: number;
  amountTotal: number;
}

export function calculateTax(amountTotal: number): TaxBreakdown {
  if (amountTotal < 0) {
    throw new Error('Total amount cannot be negative');
  }
  
  // Calculate supply using integer rounding: Math.round(total / 1.1) which is Math.round((total * 10) / 11)
  const amountSupply = Math.round((amountTotal * 10) / 11);
  const amountVat = amountTotal - amountSupply;

  return {
    amountSupply,
    amountVat,
    amountTotal,
  };
}
