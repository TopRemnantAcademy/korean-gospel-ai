import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { paymentQueue } from '../workers/queues';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import { manualInterventionSchema } from '../validators/paymentGateway.validators';
import logger from '../utils/logger';

/**
 * GET /api/admin/payments/:id/retry
 * Get retry history for a payment
 */
export async function getPaymentRetryHistory(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const payment = await prisma.payment.findUnique({
      where: { id },
      include: {
        traceLogs: {
          where: { status: 'RETRYING' },
          orderBy: { createdAt: 'desc' },
        },
      },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    return res.json(payment.traceLogs);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:id/retry
 * Manually retry a failed payment
 */
export async function retryPayment(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const payment = await prisma.payment.findUnique({
      where: { id },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    // Only allow retry for failed or cancelled payments
    if (!['FAILED', 'CANCELLED'].includes(payment.paymentStatus)) {
      return res.status(400).json({ error: 'Payment cannot be retried in current status' });
    }

    // Add to retry queue
    const job = await paymentQueue.add(
      'retry-payment',
      {
        paymentId: id,
        reason: 'MANUAL_RETRY',
        adminUserId: req.adminUser!.id,
      },
      {
        attempts: 1,
        backoff: {
          type: 'exponential',
          delay: 5000,
        },
      }
    );

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'MANUAL_PAYMENT_RETRY',
        entityType: 'Payment',
        entityId: id,
        beforeJson: { status: payment.paymentStatus } as any,
        afterJson: { jobId: job.id } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Manual payment retry initiated: ${id} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      message: 'Payment retry initiated',
      jobId: job.id,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/jobs/:jobId/retry
 * Retry a failed background job
 */
export async function retryJob(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { jobId } = req.params;

    const job = await paymentQueue.getJob(jobId);
    
    if (!job) {
      return res.status(404).json({ error: 'Job not found' });
    }

    // Retry the job
    await job.retry();

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'JOB_RETRY',
        entityType: 'Job',
        entityId: jobId,
        beforeJson: { state: 'failed' } as any,
        afterJson: { state: 'waiting' } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Job retry initiated: ${jobId} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      message: 'Job retry initiated',
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:id/intervene
 * Manual intervention for a payment
 */
export async function manualIntervention(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = manualInterventionSchema.parse(req.body);

    const payment = await prisma.payment.findUnique({
      where: { id },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    let updatedPayment = payment;

    // Execute action
    switch (validated.action) {
      case 'FORCE_COMPLETE':
        if (!validated.newStatus) {
          return res.status(400).json({ error: 'newStatus is required for FORCE_COMPLETE' });
        }
        updatedPayment = await prisma.payment.update({
          where: { id },
          data: {
            paymentStatus: validated.newStatus as any,
            metadata: {
              ...(payment.metadata as any || {}),
              manualIntervention: {
                action: validated.action,
                reason: validated.reason,
                adminUserId: req.adminUser!.id,
                timestamp: new Date().toISOString(),
              },
            },
          },
        });
        break;

      case 'MARK_FAILED':
        updatedPayment = await prisma.payment.update({
          where: { id },
          data: {
            paymentStatus: 'FAILED',
            metadata: {
              ...(payment.metadata as any || {}),
              manualIntervention: {
                action: validated.action,
                reason: validated.reason,
                adminUserId: req.adminUser!.id,
                timestamp: new Date().toISOString(),
              },
            },
          },
        });
        break;

      case 'UPDATE_STATUS':
        if (!validated.newStatus) {
          return res.status(400).json({ error: 'newStatus is required for UPDATE_STATUS' });
        }
        updatedPayment = await prisma.payment.update({
          where: { id },
          data: {
            paymentStatus: validated.newStatus as any,
            metadata: {
              ...(payment.metadata as any || {}),
              manualIntervention: {
                action: validated.action,
                reason: validated.reason,
                adminUserId: req.adminUser!.id,
                timestamp: new Date().toISOString(),
              },
            },
          },
        });
        break;

      case 'RETRY':
        // Use the retry payment function
        return retryPayment(req, res, next);
    }

    // Audit log (exclude sensitive fields)
    const sanitizePayment = (p: any) => {
      const { rawPgPayload, ...safe } = p;
      return safe;
    };

    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: `MANUAL_INTERVENTION_${validated.action}`,
        entityType: 'Payment',
        entityId: id,
        beforeJson: sanitizePayment(payment) as any,
        afterJson: sanitizePayment(updatedPayment) as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Manual intervention on payment ${id}: ${validated.action} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      message: 'Manual intervention completed',
      payment: updatedPayment,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/jobs/failed
 * Get list of failed jobs
 */
export async function getFailedJobs(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { page = '1', limit = '20' } = req.query;
    const pageNum = parseInt(page as string, 10);
    const limitNum = parseInt(limit as string, 10);
    const start = (pageNum - 1) * limitNum;

    const failedJobs = await paymentQueue.getFailed(start, start + limitNum - 1);
    const total = await paymentQueue.getFailedCount();

    const jobs = failedJobs.map(job => ({
      id: job.id,
      name: job.name,
      data: job.data,
      failedReason: job.failedReason,
      stacktrace: job.stacktrace,
      timestamp: job.finishedOn,
      attemptsMade: job.attemptsMade,
    }));

    return res.json({
      jobs,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages: Math.ceil(total / limitNum),
      },
    });
  } catch (error) {
    next(error);
  }
}
