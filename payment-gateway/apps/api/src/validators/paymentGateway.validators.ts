import { z } from 'zod';

export const paymentGatewayConfigSchema = z.object({
  // API Keys (will be encrypted)
  apiKey: z.string().min(1).max(200).optional(),
  secretKey: z.string().min(1).max(200).optional(),
  clientId: z.string().min(1).max(200).optional(),
  merchantId: z.string().min(1).max(200).optional(),
  
  // URLs
  webhookUrl: z.string().url().max(500).optional().or(z.literal('')),
  successUrl: z.string().url().max(500).optional().or(z.literal('')),
  failUrl: z.string().url().max(500).optional().or(z.literal('')),
  cancelUrl: z.string().url().max(500).optional().or(z.literal('')),
  callbackUrl: z.string().url().max(500).optional().or(z.literal('')),
  
  // Mode
  isTestMode: z.boolean().optional(),
  
  // Basic settings
  enabled: z.boolean().optional(),
  displayName: z.string().min(1).max(100).optional(),
});

export const retryPolicySchema = z.object({
  maxRetries: z.number().int().min(1).max(10),
  retryIntervals: z.array(z.number().int().min(1)).min(1).max(10),
  retryConditions: z.array(z.string()),
});

export const manualInterventionSchema = z.object({
  action: z.enum(['RETRY', 'FORCE_COMPLETE', 'MARK_FAILED', 'UPDATE_STATUS']),
  reason: z.string().min(5).max(500),
  newStatus: z.string().optional(),
  metadata: z.record(z.unknown()).optional(),
});
