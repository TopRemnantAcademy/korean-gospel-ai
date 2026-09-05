import prisma from '../repositories/db';
import logger from './logger';

type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

interface CircuitBreakerConfig {
  failureThreshold: number;
  successThreshold: number;
  timeout: number; // milliseconds
}

const DEFAULT_CONFIG: CircuitBreakerConfig = {
  failureThreshold: 5,
  successThreshold: 3,
  timeout: 60000, // 1 minute
};

/**
 * Circuit Breaker Pattern Implementation
 * Prevents cascading failures when external services are down
 */
export class CircuitBreaker {
  private serviceName: string;
  private config: CircuitBreakerConfig;

  constructor(serviceName: string, config: Partial<CircuitBreakerConfig> = {}) {
    this.serviceName = serviceName;
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Get current circuit state
   */
  private async getState(): Promise<{ status: CircuitState; failureCount: number; nextRetryAt?: Date }> {
    try {
      const record = await prisma.circuitBreaker.findUnique({
        where: { serviceName: this.serviceName },
      });

      if (!record) {
        return { status: 'CLOSED', failureCount: 0 };
      }

      return {
        status: record.status as CircuitState,
        failureCount: record.failureCount,
        nextRetryAt: record.nextRetryAt || undefined,
      };
    } catch (error) {
      logger.error('Failed to get circuit breaker state:', (error as Error).message);
      return { status: 'CLOSED', failureCount: 0 };
    }
  }

  /**
   * Update circuit state
   */
  private async updateState(
    status: CircuitState,
    failureCount: number,
    nextRetryAt?: Date
  ): Promise<void> {
    try {
      await prisma.circuitBreaker.upsert({
        where: { serviceName: this.serviceName },
        create: {
          serviceName: this.serviceName,
          status,
          failureCount,
          nextRetryAt,
        },
        update: {
          status,
          failureCount,
          nextRetryAt,
          lastFailureAt: status === 'OPEN' ? new Date() : undefined,
          lastSuccessAt: status === 'CLOSED' ? new Date() : undefined,
        },
      });
    } catch (error) {
      logger.error('Failed to update circuit breaker state:', (error as Error).message);
    }
  }

  /**
   * Check if request is allowed
   */
  async isRequestAllowed(): Promise<boolean> {
    const state = await this.getState();

    if (state.status === 'CLOSED') {
      return true;
    }

    if (state.status === 'OPEN') {
      // Check if timeout has passed
      if (state.nextRetryAt && new Date() >= state.nextRetryAt) {
        logger.info(`Circuit breaker entering HALF_OPEN state for ${this.serviceName}`);
        await this.updateState('HALF_OPEN', state.failureCount);
        return true;
      }
      return false;
    }

    // HALF_OPEN - allow one request to test
    return true;
  }

  /**
   * Record success
   */
  async recordSuccess(): Promise<void> {
    const state = await this.getState();

    if (state.status === 'HALF_OPEN') {
      const newSuccessCount = (await this.getSuccessCount()) + 1;
      
      if (newSuccessCount >= this.config.successThreshold) {
        logger.info(`Circuit breaker CLOSED for ${this.serviceName}`);
        await this.updateState('CLOSED', 0);
      }
    } else if (state.status === 'CLOSED') {
      // Reset failure count on success
      await this.updateState('CLOSED', 0);
    }
  }

  /**
   * Record failure
   */
  async recordFailure(): Promise<void> {
    const state = await this.getState();
    const newFailureCount = state.failureCount + 1;

    if (state.status === 'HALF_OPEN') {
      // Failure in half-open state -> back to open
      logger.warn(`Circuit breaker back to OPEN for ${this.serviceName}`);
      await this.updateState('OPEN', newFailureCount, new Date(Date.now() + this.config.timeout));
    } else if (newFailureCount >= this.config.failureThreshold) {
      logger.error(`Circuit breaker OPENED for ${this.serviceName} after ${newFailureCount} failures`);
      await this.updateState('OPEN', newFailureCount, new Date(Date.now() + this.config.timeout));
    } else {
      await this.updateState('CLOSED', newFailureCount);
    }
  }

  /**
   * Get success count (helper)
   */
  private async getSuccessCount(): Promise<number> {
    try {
      const record = await prisma.circuitBreaker.findUnique({
        where: { serviceName: this.serviceName },
      });
      return record?.successCount || 0;
    } catch {
      return 0;
    }
  }

  /**
   * Execute function with circuit breaker protection
   */
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (!(await this.isRequestAllowed())) {
      throw new Error(`Circuit breaker is OPEN for ${this.serviceName}. Service unavailable.`);
    }

    try {
      const result = await fn();
      await this.recordSuccess();
      return result;
    } catch (error) {
      await this.recordFailure();
      throw error;
    }
  }
}

// Pre-configured circuit breakers for external services
export const pgCircuitBreaker = new CircuitBreaker('TOSS_PAYMENTS');
export const taxCircuitBreaker = new CircuitBreaker('TAX_INVOICE_PROVIDER');
export const chinaCircuitBreaker = new CircuitBreaker('CHINA_CREDIT_API');
export const cashReceiptCircuitBreaker = new CircuitBreaker('CASH_RECEIPT_PROVIDER');
