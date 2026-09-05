import { z } from 'zod';
import { PaymentMethod, InvoiceType, CashReceiptType, CashReceiptIdentityType } from './enums';

export const socialIdentifySchema = z.object({
  provider: z.string().trim().min(1, 'Provider is required').max(50),
  providerSubject: z.string().trim().min(1, 'Provider Subject is required').max(200),
  email: z.string().trim().email('Invalid email address').optional(),
  phone: z.string().trim().regex(/^01[016789]-?\d{3,4}-?\d{4}$/, 'Invalid Korean phone number format (e.g., 010-1234-5678)').optional(),
});

export const ssoRequestSchema = z.object({
  uid: z.string().regex(/^[0-9a-f]{64}$/, 'UID must be a 64-character hex SHA-256 hash'),
  redirectUrl: z.string().url('Invalid redirect URL').refine(
    (url) => {
      try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:';
      } catch {
        return false;
      }
    },
    { message: 'Redirect URL must use HTTPS protocol' }
  ),
});

export const paymentPrepareSchema = z.object({
  userId: z.string().uuid('Invalid User ID'),
  productCode: z.string().trim().min(1, 'Product code is required').max(50),
  selectedPaymentMethod: z.nativeEnum(PaymentMethod, { required_error: 'Invalid payment method' }),
  invoiceRequested: z.boolean(),
  cashReceiptRequested: z.boolean(),
});

export const pgCallbackSchema = z.object({
  paymentKey: z.string().trim().min(1, 'Payment key is required').max(200),
  orderId: z.string().trim().min(1, 'Order ID is required').max(200),
  amount: z.number().int().positive('Amount must be a positive integer'),
  paymentMethod: z.string().trim().min(1, 'Payment method is required').max(100),
  status: z.string().trim().min(1, 'Status is required').max(50),
  invoiceRequested: z.boolean().optional(),
  cashReceiptRequested: z.boolean().optional(),
  // B2B Details
  companyRegNumber: z.string().trim().regex(/^\d{3}-\d{2}-\d{5}$/, 'Invalid Korean Business Registration Number (e.g. 123-45-67890)').optional(),
  companyName: z.string().trim().min(1).max(100).optional().or(z.literal('')),
  ceoName: z.string().trim().min(1).max(50).optional().or(z.literal('')),
  taxEmail: z.string().trim().email('Invalid tax email').max(200).optional().or(z.literal('')),
  invoiceType: z.nativeEnum(InvoiceType).optional(),
  // Cash Receipt Details
  cashReceiptType: z.nativeEnum(CashReceiptType).optional(),
  cashReceiptIdentityType: z.nativeEnum(CashReceiptIdentityType).optional(),
  cashReceiptIdentityValue: z.string().trim().min(1, 'Identity value is required if cash receipt is requested').max(50).optional(),
}).refine(
  (data) => {
    // When invoice is requested, B2B fields should be provided
    if (data.invoiceRequested) {
      return !!data.companyRegNumber && !!data.companyName && !!data.ceoName && !!data.taxEmail;
    }
    return true;
  },
  { message: 'B2B invoice fields (companyRegNumber, companyName, ceoName, taxEmail) are required when invoice is requested', path: ['invoiceRequested'] }
).refine(
  (data) => {
    // When cash receipt is requested, identity fields should be provided
    if (data.cashReceiptRequested) {
      return !!data.cashReceiptType && !!data.cashReceiptIdentityType && !!data.cashReceiptIdentityValue;
    }
    return true;
  },
  { message: 'Cash receipt fields (cashReceiptType, cashReceiptIdentityType, cashReceiptIdentityValue) are required when cash receipt is requested', path: ['cashReceiptRequested'] }
);

export const adminLoginSchema = z.object({
  email: z.string().trim().email('Invalid email address').max(200),
  password: z.string().min(6, 'Password must be at least 6 characters long').max(128, 'Password is too long'),
});

export const refundRequestSchema = z.object({
  refundAmount: z.number().int().positive('Refund amount must be a positive integer'),
  refundReason: z.string().trim().min(5, 'Reason must be at least 5 characters').max(1000),
  refundBankCode: z.string().trim().min(1).max(10).optional().or(z.literal('')),
  refundAccountNumber: z.string().trim().regex(/^[0-9-]+$/, 'Account number must contain only digits and hyphens').min(8).max(20).optional().or(z.literal('')),
  refundAccountHolder: z.string().trim().min(1).max(50).optional().or(z.literal('')),
}).refine(
  (data) => {
    // If any bank field is provided, all three must be provided
    const hasBankCode = !!data.refundBankCode;
    const hasAccountNumber = !!data.refundAccountNumber;
    const hasAccountHolder = !!data.refundAccountHolder;
    if (hasBankCode || hasAccountNumber || hasAccountHolder) {
      return hasBankCode && hasAccountNumber && hasAccountHolder;
    }
    return true;
  },
  { message: 'All bank fields (refundBankCode, refundAccountNumber, refundAccountHolder) must be provided together', path: ['refundBankCode'] }
);

export const paymentMethodConfigPatchSchema = z.object({
  enabled: z.boolean().optional(),
  displayName: z.string().trim().min(1).max(100).optional(),
  sortOrder: z.number().int().min(0).max(1000).optional(),
  supportsRefund: z.boolean().optional(),
  supportsPartialRefund: z.boolean().optional(),
  supportsCashReceipt: z.boolean().optional(),
  supportsVirtualAccountExpiry: z.boolean().optional(),
  supportsAutoRefund: z.boolean().optional(),
  metadata: z.record(z.unknown()).optional(),
});

// Webhook validation schemas
export const pgWebhookSchema = z.object({
  status: z.string().trim().min(1).max(50),
  orderId: z.string().trim().min(1).max(200),
  paymentKey: z.string().trim().min(1).max(200).optional(),
  signature: z.string().trim().min(1).max(200).optional(),
});

export const remoteWebhookSchema = z.object({
  paymentUuid: z.string().uuid(),
  status: z.enum(['SUCCESS', 'FAILED']),
  errorMessage: z.string().trim().max(1000).optional(),
  signature: z.string().trim().min(1).max(200),
});
