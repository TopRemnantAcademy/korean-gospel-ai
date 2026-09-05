import prisma from '../repositories/db';
import logger from './logger';

export type TraceStage = 'PG_PAYMENT' | 'CREDIT_DISPATCH' | 'TAX_DOCUMENT' | 'CASH_RECEIPT' | 'CHINA_WEBHOOK';
export type TraceStatus = 'INITIATED' | 'SUCCESS' | 'FAILED' | 'RETRYING';

export async function addPaymentTrace(
  paymentId: string,
  stage: TraceStage,
  status: TraceStatus,
  message: string,
  payload?: any
) {
  try {
    const trace = await prisma.paymentTraceLog.create({
      data: {
        paymentId,
        stage,
        status,
        message,
        payload: payload ? JSON.parse(JSON.stringify(payload)) : undefined,
      },
    });
    logger.info(`[AuditTrace] Payment ${paymentId} | ${stage} | ${status} | ${message}`);
    return trace;
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    logger.error(`[AuditTrace] Failed to write trace log: ${errorMessage}`);
  }
}
