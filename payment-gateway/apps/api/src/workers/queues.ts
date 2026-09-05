import { Queue, QueueEvents } from 'bullmq';
import { env } from '../config/env';
import logger from '../utils/logger';

// Shared connection options
export const connection = {
  host: new URL(env.REDIS_URL).hostname,
  port: parseInt(new URL(env.REDIS_URL).port || '6379', 10),
};

// Standard retry & backoff configuration
const defaultJobOptions = {
  attempts: 5,
  backoff: {
    type: 'exponential',
    delay: 5000, // starts at 5s delay, then 10s, 20s, 40s, 80s...
  },
  removeOnComplete: { 
    age: 3600 * 24, // keep complete jobs for 1 day
    count: 1000, // keep max 1000 completed jobs
  },
  removeOnFail: { 
    age: 3600 * 24 * 7, // keep failed jobs for 7 days
    count: 5000, // keep max 5000 failed jobs
  },
};

export const paymentQueue = new Queue('payment-tasks', {
  connection,
  defaultJobOptions,
});

export const queueEvents = new QueueEvents('payment-tasks', {
  connection,
});

queueEvents.on('failed', ({ jobId, failedReason }) => {
  logger.error(`Job failed: id=${jobId}, reason=${failedReason}`);
});

logger.info('Initialized BullMQ Queue "payment-tasks"');
