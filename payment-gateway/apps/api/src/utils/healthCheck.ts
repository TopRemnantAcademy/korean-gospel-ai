import { Request, Response } from 'express';
import prisma from '../repositories/db';
import redis from './redis';
import { paymentQueue } from '../workers/queues';
import logger from './logger';

interface HealthCheckResult {
  service: string;
  status: 'healthy' | 'unhealthy' | 'degraded';
  latency?: number;
  error?: string;
  metadata?: any;
}

/**
 * Comprehensive Health Check Service
 */
export class HealthCheckService {
  
  /**
   * Check database health
   */
  async checkDatabase(): Promise<HealthCheckResult> {
    const start = Date.now();
    try {
      await prisma.$queryRaw`SELECT 1`;
      const latency = Date.now() - start;
      
      return {
        service: 'database',
        status: latency < 100 ? 'healthy' : 'degraded',
        latency,
        metadata: { type: 'postgresql' },
      };
    } catch (error) {
      return {
        service: 'database',
        status: 'unhealthy',
        error: (error as Error).message,
      };
    }
  }

  /**
   * Check Redis health
   */
  async checkRedis(): Promise<HealthCheckResult> {
    const start = Date.now();
    try {
      await redis.ping();
      const latency = Date.now() - start;
      
      return {
        service: 'redis',
        status: latency < 50 ? 'healthy' : 'degraded',
        latency,
      };
    } catch (error) {
      return {
        service: 'redis',
        status: 'unhealthy',
        error: (error as Error).message,
      };
    }
  }

  /**
   * Check queue health
   */
  async checkQueue(): Promise<HealthCheckResult> {
    try {
      const [waiting, active, failed, completed] = await Promise.all([
        paymentQueue.getWaitingCount(),
        paymentQueue.getActiveCount(),
        paymentQueue.getFailedCount(),
        paymentQueue.getCompletedCount(),
      ]);

      const status = failed > 100 ? 'degraded' : 'healthy';
      
      return {
        service: 'queue',
        status,
        metadata: {
          waiting,
          active,
          failed,
          completed,
          name: 'payment-tasks',
        },
      };
    } catch (error) {
      return {
        service: 'queue',
        status: 'unhealthy',
        error: (error as Error).message,
      };
    }
  }

  /**
   * Check memory usage
   */
  checkMemory(): HealthCheckResult {
    const usage = process.memoryUsage();
    const heapUsedMB = Math.round(usage.heapUsed / 1024 / 1024);
    const heapTotalMB = Math.round(usage.heapTotal / 1024 / 1024);
    const usagePercent = (usage.heapUsed / usage.heapTotal) * 100;

    return {
      service: 'memory',
      status: usagePercent > 90 ? 'unhealthy' : usagePercent > 75 ? 'degraded' : 'healthy',
      metadata: {
        heapUsedMB,
        heapTotalMB,
        usagePercent: Math.round(usagePercent),
        rssMB: Math.round(usage.rss / 1024 / 1024),
      },
    };
  }

  /**
   * Run all health checks
   */
  async runAllChecks(): Promise<{
    status: 'healthy' | 'unhealthy' | 'degraded';
    checks: HealthCheckResult[];
    timestamp: string;
  }> {
    const checks = await Promise.all([
      this.checkDatabase(),
      this.checkRedis(),
      this.checkQueue(),
      Promise.resolve(this.checkMemory()),
    ]);

    // Determine overall status
    const hasUnhealthy = checks.some(c => c.status === 'unhealthy');
    const hasDegraded = checks.some(c => c.status === 'degraded');
    
    const status = hasUnhealthy ? 'unhealthy' : hasDegraded ? 'degraded' : 'healthy';

    return {
      status,
      checks,
      timestamp: new Date().toISOString(),
    };
  }
}

const healthCheckService = new HealthCheckService();

/**
 * Health check endpoint handler
 */
export async function healthCheckHandler(req: Request, res: Response) {
  try {
    const result = await healthCheckService.runAllChecks();
    
    const statusCode = result.status === 'healthy' ? 200 : 
                       result.status === 'degraded' ? 200 : 503;
    
    res.status(statusCode).json(result);
  } catch (error) {
    logger.error('Health check failed:', (error as Error).message);
    res.status(503).json({
      status: 'unhealthy',
      error: 'Health check failed',
      timestamp: new Date().toISOString(),
    });
  }
}

export default healthCheckService;
