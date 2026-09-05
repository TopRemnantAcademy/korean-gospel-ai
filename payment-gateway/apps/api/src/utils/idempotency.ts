import prisma from '../repositories/db';
import logger from './logger';

const IDEMPOTENCY_KEY_TTL_SECONDS = 86400; // 24 hours

/**
 * Idempotency Service
 * Ensures operations can be safely retried without duplication
 */
export class IdempotencyService {
  
  /**
   * Check if an idempotency key exists and return cached response
   */
  async checkIdempotencyKey(key: string): Promise<{ exists: boolean; response?: any }> {
    try {
      const record = await prisma.idempotencyKey.findUnique({
        where: { key },
      });

      if (!record) {
        return { exists: false };
      }

      // Check if expired
      if (new Date() > record.expiresAt) {
        await prisma.idempotencyKey.delete({ where: { key } });
        return { exists: false };
      }

      logger.info(`Idempotency key hit: ${key}`);
      return { exists: true, response: record.response };
    } catch (error) {
      logger.error('Failed to check idempotency key:', (error as Error).message);
      return { exists: false };
    }
  }

  /**
   * Store idempotency key with response
   */
  async storeIdempotencyKey(
    key: string,
    operation: string,
    requestBody: any,
    response: any
  ): Promise<void> {
    try {
      const expiresAt = new Date(Date.now() + IDEMPOTENCY_KEY_TTL_SECONDS * 1000);
      
      await prisma.idempotencyKey.create({
        data: {
          key,
          operation,
          requestBody,
          response,
          expiresAt,
        },
      });
    } catch (error) {
      logger.error('Failed to store idempotency key:', (error as Error).message);
    }
  }

  /**
   * Generate idempotency key for operation
   */
  generateKey(operation: string, identifier: string): string {
    return `${operation}:${identifier}`;
  }

  /**
   * Clean up expired keys
   */
  async cleanupExpiredKeys(): Promise<void> {
    try {
      const result = await prisma.idempotencyKey.deleteMany({
        where: {
          expiresAt: { lt: new Date() },
        },
      });
      logger.info(`Cleaned up ${result.count} expired idempotency keys`);
    } catch (error) {
      logger.error('Failed to cleanup idempotency keys:', (error as Error).message);
    }
  }
}

export default new IdempotencyService();
