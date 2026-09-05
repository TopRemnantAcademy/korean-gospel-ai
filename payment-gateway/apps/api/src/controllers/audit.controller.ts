import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import logger from '../utils/logger';
import { z } from 'zod';

const auditLogQuerySchema = z.object({
  action: z.string().optional(),
  entityType: z.string().optional(),
  adminUserId: z.string().optional(),
  startDate: z.string().optional(),
  endDate: z.string().optional(),
  page: z.string().optional(),
  limit: z.string().optional(),
});

/**
 * GET /api/admin/v2/audit-logs
 * Get audit logs with filters
 */
export async function getAuditLogs(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const query = auditLogQuerySchema.parse(req.query);
    const page = parseInt(query.page || '1', 10);
    const limit = parseInt(query.limit || '20', 10);
    const skip = (page - 1) * limit;

    const where: any = {};

    if (query.action) {
      where.action = { contains: query.action, mode: 'insensitive' };
    }
    if (query.entityType) {
      where.entityType = query.entityType;
    }
    if (query.adminUserId) {
      where.adminUserId = query.adminUserId;
    }
    if (query.startDate || query.endDate) {
      where.createdAt = {};
      if (query.startDate) {
        where.createdAt.gte = new Date(query.startDate);
      }
      if (query.endDate) {
        where.createdAt.lte = new Date(query.endDate);
      }
    }

    const [logs, total] = await Promise.all([
      prisma.adminAuditLog.findMany({
        where,
        include: {
          adminUser: {
            select: {
              id: true,
              email: true,
              role: true,
            },
          },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.adminAuditLog.count({ where }),
    ]);

    return res.json({
      logs,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/v2/audit-logs/:id
 * Get audit log details
 */
export async function getAuditLogDetails(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const log = await prisma.adminAuditLog.findUnique({
      where: { id },
      include: {
        adminUser: {
          select: {
            id: true,
            email: true,
            role: true,
          },
        },
      },
    });

    if (!log) {
      return res.status(404).json({ error: 'Audit log not found' });
    }

    return res.json(log);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/v2/audit-logs/export
 * Export audit logs as CSV
 */
export async function exportAuditLogs(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const query = auditLogQuerySchema.parse(req.query);

    const where: any = {};

    if (query.action) {
      where.action = { contains: query.action, mode: 'insensitive' };
    }
    if (query.entityType) {
      where.entityType = query.entityType;
    }
    if (query.adminUserId) {
      where.adminUserId = query.adminUserId;
    }
    if (query.startDate || query.endDate) {
      where.createdAt = {};
      if (query.startDate) {
        where.createdAt.gte = new Date(query.startDate);
      }
      if (query.endDate) {
        where.createdAt.lte = new Date(query.endDate);
      }
    }

    const logs = await prisma.adminAuditLog.findMany({
      where,
      include: {
        adminUser: {
          select: {
            email: true,
          },
        },
      },
      orderBy: { createdAt: 'desc' },
      take: 10000, // Limit to 10,000 rows
    });

    // Convert to CSV
    const headers = ['ID', 'Action', 'Entity Type', 'Entity ID', 'Admin Email', 'IP Address', 'Created At'];
    const sanitizeCsvCell = (cell: string): string => {
      // Escape double quotes and prevent CSV injection
      const escaped = cell.replace(/"/g, '""');
      const trimmed = escaped.trimStart();
      if (trimmed.startsWith('=') || trimmed.startsWith('+') || trimmed.startsWith('-') || trimmed.startsWith('@')) {
        return `'${escaped}`;
      }
      return escaped;
    };
    const rows = logs.map(log => [
      log.id,
      log.action,
      log.entityType,
      log.entityId,
      log.adminUser?.email || 'SYSTEM',
      log.ipAddress,
      log.createdAt.toISOString(),
    ]);

    const csv = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${sanitizeCsvCell(cell)}"`).join(',')),
    ].join('\n');

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'EXPORT_AUDIT_LOGS',
        entityType: 'AuditLog',
        entityId: 'EXPORT',
        afterJson: { count: logs.length, filters: query } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Audit logs exported: ${logs.length} rows by ${req.adminUser!.email}`);

    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename="audit-logs-${new Date().toISOString().split('T')[0]}.csv"`);
    return res.send(csv);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/v2/audit-logs/stats
 * Get audit log statistics
 */
export async function getAuditLogStats(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { startDate, endDate } = req.query;

    const where: any = {};
    if (startDate || endDate) {
      where.createdAt = {};
      if (startDate) {
        where.createdAt.gte = new Date(startDate as string);
      }
      if (endDate) {
        where.createdAt.lte = new Date(endDate as string);
      }
    }

    // Get action counts
    const actionCounts = await prisma.adminAuditLog.groupBy({
      by: ['action'],
      where,
      _count: {
        id: true,
      },
      orderBy: {
        _count: {
          id: 'desc',
        },
      },
      take: 20,
    });

    // Get entity type counts
    const entityTypeCounts = await prisma.adminAuditLog.groupBy({
      by: ['entityType'],
      where,
      _count: {
        id: true,
      },
      orderBy: {
        _count: {
          id: 'desc',
        },
      },
    });

    // Get admin user activity
    const adminActivity = await prisma.adminAuditLog.groupBy({
      by: ['adminUserId'],
      where,
      _count: {
        id: true,
      },
      orderBy: {
        _count: {
          id: 'desc',
        },
      },
      take: 10,
    });

    // Get admin user details
    const adminUserIds = adminActivity.map(a => a.adminUserId).filter(Boolean) as string[];
    const adminUsers = await prisma.adminUser.findMany({
      where: { id: { in: adminUserIds } },
      select: { id: true, email: true },
    });

    const adminActivityWithDetails = adminActivity.map(a => ({
      adminUser: adminUsers.find(u => u.id === a.adminUserId),
      count: a._count.id,
    }));

    return res.json({
      actionCounts: actionCounts.map(a => ({
        action: a.action,
        count: a._count.id,
      })),
      entityTypeCounts: entityTypeCounts.map(e => ({
        entityType: e.entityType,
        count: e._count.id,
      })),
      adminActivity: adminActivityWithDetails,
    });
  } catch (error) {
    next(error);
  }
}
