import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { paymentQueue } from '../workers/queues';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import logger from '../utils/logger';

/**
 * GET /api/admin/monitoring/dashboard
 * Get real-time monitoring dashboard data
 */
export async function getMonitoringDashboard(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

    // Get payment statistics for last hour
    const [totalPayments, successfulPayments, failedPayments] = await Promise.all([
      prisma.payment.count({
        where: { createdAt: { gte: oneHourAgo } },
      }),
      prisma.payment.count({
        where: {
          createdAt: { gte: oneHourAgo },
          paymentStatus: 'PAID',
        },
      }),
      prisma.payment.count({
        where: {
          createdAt: { gte: oneHourAgo },
          paymentStatus: { in: ['FAILED', 'CANCELLED'] },
        },
      }),
    ]);

    // Calculate average processing time
    const recentPayments = await prisma.payment.findMany({
      where: {
        createdAt: { gte: oneHourAgo },
        paymentStatus: 'PAID',
        paidAt: { not: null },
      },
      select: {
        createdAt: true,
        paidAt: true,
      },
      take: 100,
    });

    const avgProcessingTime = recentPayments.length > 0
      ? recentPayments.reduce((sum, p) => {
          const duration = p.paidAt!.getTime() - p.createdAt.getTime();
          return sum + duration;
        }, 0) / recentPayments.length
      : 0;

    // Get queue statistics
    const [waiting, active, failed, completed] = await Promise.all([
      paymentQueue.getWaitingCount(),
      paymentQueue.getActiveCount(),
      paymentQueue.getFailedCount(),
      paymentQueue.getCompletedCount(),
    ]);

    // Get recent failed jobs
    const failedJobs = await paymentQueue.getFailed(0, 10);

    const dashboard = {
      payments: {
        total: totalPayments,
        successful: successfulPayments,
        failed: failedPayments,
        successRate: totalPayments > 0 ? (successfulPayments / totalPayments * 100).toFixed(2) : '0',
        avgProcessingTime: Math.round(avgProcessingTime),
      },
      queue: {
        waiting,
        active,
        failed,
        completed,
        recentFailures: failedJobs.map(job => ({
          id: job.id,
          name: job.name,
          failedReason: job.failedReason,
          timestamp: job.finishedOn,
        })),
      },
      timestamp: now.toISOString(),
    };

    return res.json(dashboard);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/monitoring/services
 * Get external services status
 */
export async function getServicesStatus(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    // Check database
    let dbStatus = 'healthy';
    let dbLatency = 0;
    try {
      const start = Date.now();
      await prisma.$queryRaw`SELECT 1`;
      dbLatency = Date.now() - start;
    } catch {
      dbStatus = 'unhealthy';
    }

    // Check Redis
    let redisStatus = 'healthy';
    let redisLatency = 0;
    try {
      const { default: redis } = await import('../utils/redis');
      const start = Date.now();
      await redis.ping();
      redisLatency = Date.now() - start;
    } catch {
      redisStatus = 'unhealthy';
    }

    // Check payment gateways
    const paymentGateways = await prisma.paymentMethodConfig.findMany({
      where: { enabled: true },
      select: {
        paymentMethod: true,
        displayName: true,
        isTestMode: true,
        apiKeyEncrypted: true,
      },
    });

    const services = {
      database: {
        status: dbStatus,
        latency: dbLatency,
      },
      redis: {
        status: redisStatus,
        latency: redisLatency,
      },
      paymentGateways: paymentGateways.map(pg => ({
        name: pg.paymentMethod,
        displayName: pg.displayName,
        status: pg.apiKeyEncrypted ? 'configured' : 'not_configured',
        mode: pg.isTestMode ? 'TEST' : 'PRODUCTION',
      })),
      timestamp: new Date().toISOString(),
    };

    return res.json(services);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/monitoring/alerts
 * Get system alerts
 */
export async function getSystemAlerts(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const alerts: any[] = [];

    // Check for high failure rate
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

    const [total, failed] = await Promise.all([
      prisma.payment.count({
        where: { createdAt: { gte: oneHourAgo } },
      }),
      prisma.payment.count({
        where: {
          createdAt: { gte: oneHourAgo },
          paymentStatus: 'FAILED',
        },
      }),
    ]);

    if (total > 10 && (failed / total) > 0.1) {
      alerts.push({
        type: 'HIGH_FAILURE_RATE',
        severity: 'HIGH',
        message: `결제 실패율이 높습니다: ${(failed / total * 100).toFixed(2)}%`,
        timestamp: now.toISOString(),
      });
    }

    // Check for queue backup
    const waiting = await paymentQueue.getWaitingCount();
    if (waiting > 100) {
      alerts.push({
        type: 'QUEUE_BACKUP',
        severity: 'MEDIUM',
        message: `큐 대기열이 많습니다: ${waiting}개`,
        timestamp: now.toISOString(),
      });
    }

    // Check for failed jobs
    const failedJobs = await paymentQueue.getFailedCount();
    if (failedJobs > 10) {
      alerts.push({
        type: 'FAILED_JOBS',
        severity: 'HIGH',
        message: `실패한 작업이 많습니다: ${failedJobs}개`,
        timestamp: now.toISOString(),
      });
    }

    return res.json({ alerts });
  } catch (error) {
    next(error);
  }
}
