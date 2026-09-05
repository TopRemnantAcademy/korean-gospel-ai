import { Router } from 'express';
import { 
  adminLogin, 
  getDashboardMetrics, 
  getPayments, 
  getPaymentDetail, 
  getTaxDocuments, 
  getCashReceipts, 
  getCreditDispatches, 
  getConsents, 
  getExternalCallLogs, 
  retryCredit, 
  retryTaxDocument, 
  retryCashReceipt, 
  overrideWebhook,
  processRefund, 
  updatePaymentMethodConfig, 
  getSettings,
  getAdminAuditLogs,
  decryptPaymentPII,
  getPaymentTraces
} from '../controllers/admin.controller';
import { adminAuthRequired, roleRequired } from '../middlewares/auth.middleware';
import { authLimiter } from '../middlewares/rateLimiter';
import { AdminRole } from '@gospel-pay/shared';

import {
  importRemittances,
  runReconciliation,
  getReconciliationLogs,
  downloadReconciliationReport
} from '../controllers/reconciliation.controller';

const router = Router();

// Public Admin Route
router.post('/admin/auth/login', authLimiter, adminLogin);

// Protected Admin Routes (Require Admin Authentication)
router.use('/admin', adminAuthRequired as any);

// Dashboard
router.get(
  '/admin/dashboard',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getDashboardMetrics as any
);

// Payment Listings
router.get(
  '/admin/payments',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getPayments as any
);
router.get(
  '/admin/payments/:paymentUuid',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getPaymentDetail as any
);

// Documents & Logs
router.get(
  '/admin/tax-documents',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.READONLY]),
  getTaxDocuments as any
);
router.get(
  '/admin/cash-receipts',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.READONLY]),
  getCashReceipts as any
);
router.get(
  '/admin/credit-dispatches',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getCreditDispatches as any
);
router.get(
  '/admin/consents',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.READONLY]),
  getConsents as any
);
router.get(
  '/admin/external-call-logs',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getExternalCallLogs as any
);
router.get(
  '/admin/audit-logs',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.READONLY]),
  getAdminAuditLogs as any
);

// Configuration & settings
router.get(
  '/admin/settings',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getSettings as any
);
router.patch(
  '/admin/payment-method-configs/:id',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.DEVELOPER]),
  updatePaymentMethodConfig as any
);

// Actions & Retry Job Commands
router.post(
  '/admin/payments/:paymentUuid/retry-credit',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.DEVELOPER]),
  retryCredit as any
);
router.post(
  '/admin/payments/:paymentUuid/retry-tax-document',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  retryTaxDocument as any
);
router.post(
  '/admin/payments/:paymentUuid/retry-cash-receipt',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  retryCashReceipt as any
);
router.post(
  '/admin/payments/:paymentUuid/override-webhook',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.DEVELOPER]),
  overrideWebhook as any
);
router.post(
  '/admin/payments/:paymentUuid/refund',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  processRefund as any
);
router.post(
  '/admin/payments/:paymentUuid/decrypt',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  decryptPaymentPII as any
);

// Reconciliation & Report
router.post(
  '/admin/reconciliation/import',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  importRemittances as any
);
router.post(
  '/admin/reconciliation/run',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN]),
  runReconciliation as any
);
router.get(
  '/admin/reconciliation/logs',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.READONLY]),
  getReconciliationLogs as any
);
router.get(
  '/admin/reconciliation/report',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.READONLY]),
  downloadReconciliationReport as any
);

// Payment audit tracing
router.get(
  '/admin/payments/:paymentUuid/traces',
  roleRequired([AdminRole.SUPER_ADMIN, AdminRole.OPS_ADMIN, AdminRole.FINANCE_ADMIN, AdminRole.DEVELOPER, AdminRole.READONLY]),
  getPaymentTraces as any
);

export default router;
