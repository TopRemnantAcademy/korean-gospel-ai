import { Router } from 'express';
import { requireAdminAuth, requireSuperAdmin } from '../middlewares/auth.middleware';
import {
  getPaymentGateways,
  getPaymentGateway,
  updatePaymentGateway,
  testPaymentGateway,
} from '../controllers/paymentGateway.controller';
import {
  getMonitoringDashboard,
  getServicesStatus,
  getSystemAlerts,
} from '../controllers/monitoring.controller';
import {
  getPaymentRetryHistory,
  retryPayment,
  retryJob,
  manualIntervention,
  getFailedJobs,
} from '../controllers/retry.controller';
import {
  getRefunds,
  getPaymentRefundInfo,
  processRefund,
  getRefundDetails,
} from '../controllers/refund.controller';
import {
  getAdminUsers,
  createAdminUser,
  updateAdminUser,
  resetAdminPassword,
  getUsers,
  getUserDetails,
} from '../controllers/userManagement.controller';
import {
  getReconciliationSummary,
  runAutoReconciliation,
  getDiscrepancies,
} from '../controllers/reconciliationAdvanced.controller';
import {
  getAuditLogs,
  getAuditLogDetails,
  exportAuditLogs,
  getAuditLogStats,
} from '../controllers/audit.controller';
import {
  getBackups,
  createBackup,
  downloadBackup,
  deleteBackup,
  restoreBackup,
} from '../controllers/backup.controller';

const router = Router();

// All routes require admin authentication
router.use(requireAdminAuth);

// Payment Gateway Configuration Routes
router.get('/payment-gateways', getPaymentGateways);
router.get('/payment-gateways/:id', getPaymentGateway);
router.patch('/payment-gateways/:id', requireSuperAdmin, updatePaymentGateway);
router.post('/payment-gateways/:id/test', requireSuperAdmin, testPaymentGateway);

// Monitoring Routes
router.get('/monitoring/dashboard', getMonitoringDashboard);
router.get('/monitoring/services', getServicesStatus);
router.get('/monitoring/alerts', getSystemAlerts);

// Retry and Manual Intervention Routes
router.get('/payments/:id/retry', getPaymentRetryHistory);
router.post('/payments/:id/retry', retryPayment);
router.post('/payments/:id/intervene', requireSuperAdmin, manualIntervention);
router.get('/jobs/failed', getFailedJobs);
router.post('/jobs/:jobId/retry', retryJob);

// Refund Management Routes (prefixed with /v2 to avoid conflict with admin.routes.ts)
router.get('/v2/refunds', getRefunds);
router.get('/v2/refunds/:id', getRefundDetails);
router.get('/v2/payments/:id/refund-info', getPaymentRefundInfo);
router.post('/v2/payments/:id/refund', processRefund);

// User Management Routes
router.get('/admin-users', requireSuperAdmin, getAdminUsers);
router.post('/admin-users', requireSuperAdmin, createAdminUser);
router.patch('/admin-users/:id', requireSuperAdmin, updateAdminUser);
router.post('/admin-users/:id/reset-password', requireSuperAdmin, resetAdminPassword);
router.get('/users', getUsers);
router.get('/users/:id', getUserDetails);

// Reconciliation Routes (prefixed with /v2 to avoid conflict with admin.routes.ts)
router.get('/v2/reconciliation/summary/:targetMonth', getReconciliationSummary);
router.post('/v2/reconciliation/auto', runAutoReconciliation);
router.get('/v2/reconciliation/discrepancies/:targetMonth', getDiscrepancies);

// Audit Log Routes (prefixed with /v2 to avoid conflict with admin.routes.ts)
// stats before :id to avoid route conflict
router.get('/v2/audit-logs', getAuditLogs);
router.get('/v2/audit-logs/stats', getAuditLogStats);
router.get('/v2/audit-logs/export', exportAuditLogs);
router.get('/v2/audit-logs/:id', getAuditLogDetails);

// Backup Routes
router.get('/backups', requireSuperAdmin, getBackups);
router.post('/backups', requireSuperAdmin, createBackup);
router.get('/backups/:filename/download', requireSuperAdmin, downloadBackup);
router.delete('/backups/:filename', requireSuperAdmin, deleteBackup);
router.post('/backups/:filename/restore', requireSuperAdmin, restoreBackup);

export default router;
