export interface Product {
  code: string;
  name: string;
  amountTotal: number;
  creditAmount: number;
}

export const PRODUCTS: Record<string, Product> = {
  CREDIT_100: {
    code: 'CREDIT_100',
    name: '100 Credits Package',
    amountTotal: 11000, // KRW (10,000 supply + 1,000 VAT)
    creditAmount: 100,
  },
  CREDIT_500: {
    code: 'CREDIT_500',
    name: '500 Credits Package',
    amountTotal: 55000, // KRW (50,000 supply + 5,000 VAT)
    creditAmount: 500,
  },
  CREDIT_1000: {
    code: 'CREDIT_1000',
    name: '1,000 Credits Package',
    amountTotal: 110000, // KRW (100,000 supply + 10,000 VAT)
    creditAmount: 1000,
  },
};

export const BANK_CODES: Record<string, string> = {
  '004': '국민은행',
  '088': '신한은행',
  '020': '우리은행',
  '003': '기업은행',
  '011': '농협은행',
  '081': '하나은행',
  '090': '카카오뱅크',
  '092': '토스뱅크',
  '089': '케이뱅크',
};
