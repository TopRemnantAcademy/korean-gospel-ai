import { z } from 'zod';
import {
  socialIdentifySchema,
  ssoRequestSchema,
  paymentPrepareSchema,
  pgCallbackSchema,
  adminLoginSchema,
  refundRequestSchema,
  paymentMethodConfigPatchSchema,
} from './validators';

// Derive request types from Zod schemas to prevent type-validator drift
export type SocialIdentifyRequest = z.infer<typeof socialIdentifySchema>;
export type SSORequest = z.infer<typeof ssoRequestSchema>;
export type PaymentPrepareRequest = z.infer<typeof paymentPrepareSchema>;
export type PGCallbackRequest = z.infer<typeof pgCallbackSchema>;
export type AdminLoginRequest = z.infer<typeof adminLoginSchema>;
export type RefundRequest = z.infer<typeof refundRequestSchema>;
export type PaymentMethodConfigPatch = z.infer<typeof paymentMethodConfigPatchSchema>;

// Response types (not derived from schemas — these are output shapes)
export interface SocialIdentifyResponse {
  userId: string;
  uid: string;
  emailMasked?: string;
  phoneMasked?: string;
}

export interface SSOResponse {
  token: string;
  redirectUrl: string;
}

export interface PaymentPrepareResponse {
  paymentOrderUuid: string;
  pgOrderId: string;
  amountTotal: number;
  productName: string;
}

export interface AdminLoginResponse {
  token: string;
  user: {
    id: string;
    email: string;
    role: string;
  };
}
