import prisma from '../repositories/db';
import logger from './logger';
import { env } from '../config/env';

export interface NotificationPayload {
  type: 'PAYMENT_FAILED' | 'PAYMENT_SUCCESS' | 'WEBHOOK_FAILED' | 'SYSTEM_ERROR' | 'SUSPICIOUS_ACTIVITY' | 'REFUND_PROCESSED';
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  title: string;
  message: string;
  metadata?: any;
  paymentId?: string;
  userId?: string;
}

/**
 * Notification Service
 * Handles all system notifications and alerts
 */
export class NotificationService {
  
  /**
   * Create a notification record
   */
  async createNotification(payload: NotificationPayload): Promise<void> {
    try {
      await prisma.notification.create({
        data: {
          type: payload.type,
          severity: payload.severity,
          title: payload.title,
          message: payload.message,
          metadata: payload.metadata || {},
          paymentId: payload.paymentId,
          userId: payload.userId,
          isRead: false,
        },
      });

      // Log critical notifications
      if (payload.severity === 'CRITICAL' || payload.severity === 'HIGH') {
        logger.error(`[NOTIFICATION] ${payload.type}: ${payload.message}`, payload.metadata);
      } else {
        logger.info(`[NOTIFICATION] ${payload.type}: ${payload.message}`);
      }

      // In production, this would send emails/SMS/webhooks
      if (env.NODE_ENV === 'production' && payload.severity === 'CRITICAL') {
        await this.sendCriticalAlert(payload);
      }
    } catch (error) {
      logger.error('Failed to create notification:', (error as Error).message);
    }
  }

  /**
   * Send critical alert (placeholder for email/SMS integration)
   */
  private async sendCriticalAlert(payload: NotificationPayload): Promise<void> {
    // TODO: Integrate with email service (SendGrid, AWS SES, etc.)
    // TODO: Integrate with SMS service (Twilio, etc.)
    // TODO: Integrate with Slack/Discord webhooks
    logger.error(`[CRITICAL ALERT] ${payload.title}: ${payload.message}`);
  }

  /**
   * Notify payment failure
   */
  async notifyPaymentFailed(paymentId: string, reason: string, metadata?: any): Promise<void> {
    await this.createNotification({
      type: 'PAYMENT_FAILED',
      severity: 'HIGH',
      title: '결제 실패',
      message: `결제 처리 중 오류가 발생했습니다: ${reason}`,
      metadata,
      paymentId,
    });
  }

  /**
   * Notify webhook failure
   */
  async notifyWebhookFailed(paymentId: string, webhookType: string, error: string): Promise<void> {
    await this.createNotification({
      type: 'WEBHOOK_FAILED',
      severity: 'CRITICAL',
      title: '웹훅 처리 실패',
      message: `${webhookType} 웹훅 처리 실패: ${error}`,
      metadata: { webhookType, error },
      paymentId,
    });
  }

  /**
   * Notify suspicious activity
   */
  async notifySuspiciousActivity(userId: string, activity: string, metadata?: any): Promise<void> {
    await this.createNotification({
      type: 'SUSPICIOUS_ACTIVITY',
      severity: 'CRITICAL',
      title: '의심스러운 활동 감지',
      message: activity,
      metadata,
      userId,
    });
  }

  /**
   * Get unread notifications
   */
  async getUnreadNotifications(limit: number = 50) {
    return await prisma.notification.findMany({
      where: { isRead: false },
      orderBy: { createdAt: 'desc' },
      take: limit,
    });
  }

  /**
   * Mark notification as read
   */
  async markAsRead(notificationId: string): Promise<void> {
    await prisma.notification.update({
      where: { id: notificationId },
      data: { isRead: true, readAt: new Date() },
    });
  }
}

export default new NotificationService();
