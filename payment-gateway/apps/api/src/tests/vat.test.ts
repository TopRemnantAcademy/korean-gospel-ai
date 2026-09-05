import { calculateTax } from '../services/vat.service';

describe('VAT Calculation Service', () => {
  test('Standard amounts should divide supply and VAT correctly', () => {
    // 11,000 KRW -> 10,000 supply, 1,000 VAT
    const breakdown = calculateTax(11000);
    expect(breakdown.amountSupply).toBe(10000);
    expect(breakdown.amountVat).toBe(1000);
    expect(breakdown.amountSupply + breakdown.amountVat).toBe(11000);

    // Integers check
    expect(Number.isInteger(breakdown.amountSupply)).toBe(true);
    expect(Number.isInteger(breakdown.amountVat)).toBe(true);
  });

  test('Complex odd amounts should not violate supply + VAT = total rule', () => {
    const testAmounts = [10000, 10001, 10009, 55555, 99999, 1234567, 3, 0];
    
    for (const amount of testAmounts) {
      const breakdown = calculateTax(amount);
      
      expect(Number.isInteger(breakdown.amountSupply)).toBe(true);
      expect(Number.isInteger(breakdown.amountVat)).toBe(true);
      expect(breakdown.amountSupply + breakdown.amountVat).toBe(amount);
    }
  });

  test('Negative amount should throw error', () => {
    expect(() => calculateTax(-100)).toThrow();
  });
});
