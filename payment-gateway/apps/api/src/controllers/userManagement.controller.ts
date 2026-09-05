import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import bcrypt from 'bcryptjs';
import { z } from 'zod';
import logger from '../utils/logger';

const BCRYPT_ROUNDS = 12;

const createAdminUserSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(100),
  role: z.enum(['SUPER_ADMIN', 'OPS_ADMIN', 'FINANCE_ADMIN', 'DEVELOPER', 'READONLY']),
});

const updateAdminUserSchema = z.object({
  role: z.enum(['SUPER_ADMIN', 'OPS_ADMIN', 'FINANCE_ADMIN', 'DEVELOPER', 'READONLY']).optional(),
  isActive: z.boolean().optional(),
});

const updateAdminPasswordSchema = z.object({
  newPassword: z.string().min(8).max(100),
});

/**
 * GET /api/admin/admin-users
 * Get list of admin users
 */
export async function getAdminUsers(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const adminUsers = await prisma.adminUser.findMany({
      select: {
        id: true,
        email: true,
        role: true,
        isActive: true,
        createdAt: true,
        lastLoginAt: true,
      },
      orderBy: { createdAt: 'desc' },
    });

    return res.json(adminUsers);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/admin-users
 * Create new admin user (SUPER_ADMIN only)
 */
export async function createAdminUser(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const validated = createAdminUserSchema.parse(req.body);

    // Check if email already exists
    const existing = await prisma.adminUser.findUnique({
      where: { email: validated.email },
    });

    if (existing) {
      return res.status(400).json({ error: 'Email already exists' });
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(validated.password, BCRYPT_ROUNDS);

    // Create admin user
    const adminUser = await prisma.adminUser.create({
      data: {
        email: validated.email,
        passwordHash: hashedPassword,
        role: validated.role,
        isActive: true,
      },
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'CREATE_ADMIN_USER',
        entityType: 'AdminUser',
        entityId: adminUser.id,
        afterJson: {
          email: adminUser.email,
          role: adminUser.role,
        } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Admin user created: ${adminUser.email} by ${req.adminUser!.email}`);

    return res.status(201).json({
      id: adminUser.id,
      email: adminUser.email,
      role: adminUser.role,
      isActive: adminUser.isActive,
      createdAt: adminUser.createdAt,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * PATCH /api/admin/admin-users/:id
 * Update admin user (SUPER_ADMIN only)
 */
export async function updateAdminUser(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = updateAdminUserSchema.parse(req.body);

    const existing = await prisma.adminUser.findUnique({
      where: { id },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Admin user not found' });
    }

    // Prevent deactivating self
    if (id === req.adminUser!.id && validated.isActive === false) {
      return res.status(400).json({ error: 'Cannot deactivate your own account' });
    }

    // Prevent changing own role
    if (id === req.adminUser!.id && validated.role) {
      return res.status(400).json({ error: 'Cannot change your own role' });
    }

    const updated = await prisma.adminUser.update({
      where: { id },
      data: validated,
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'UPDATE_ADMIN_USER',
        entityType: 'AdminUser',
        entityId: id,
        beforeJson: {
          role: existing.role,
          isActive: existing.isActive,
        } as any,
        afterJson: {
          role: updated.role,
          isActive: updated.isActive,
        } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Admin user updated: ${updated.email} by ${req.adminUser!.email}`);

    return res.json({
      id: updated.id,
      email: updated.email,
      role: updated.role,
      isActive: updated.isActive,
      createdAt: updated.createdAt,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/admin-users/:id/reset-password
 * Reset admin user password (SUPER_ADMIN only)
 */
export async function resetAdminPassword(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = updateAdminPasswordSchema.parse(req.body);

    const existing = await prisma.adminUser.findUnique({
      where: { id },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Admin user not found' });
    }

    // Hash new password
    const hashedPassword = await bcrypt.hash(validated.newPassword, BCRYPT_ROUNDS);

    // Update password
    await prisma.adminUser.update({
      where: { id },
      data: { passwordHash: hashedPassword },
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'RESET_ADMIN_PASSWORD',
        entityType: 'AdminUser',
        entityId: id,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Admin password reset: ${existing.email} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      message: 'Password reset successfully',
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/users
 * Get list of regular users (customers)
 */
export async function getUsers(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { page = '1', limit = '20' } = req.query;
    const pageNum = parseInt(page as string, 10);
    const limitNum = parseInt(limit as string, 10);
    const skip = (pageNum - 1) * limitNum;

    const [users, total] = await Promise.all([
      prisma.user.findMany({
        select: {
          id: true,
          uid: true,
          createdAt: true,
          deletedAt: true,
          _count: {
            select: {
              payments: true,
            },
          },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limitNum,
      }),
      prisma.user.count(),
    ]);

    // Get total payment amount for each user
    const usersWithStats = await Promise.all(
      users.map(async (user) => {
        const totalAmount = await prisma.payment.aggregate({
          where: {
            userId: user.id,
            paymentStatus: 'PAID',
          },
          _sum: {
            amountTotal: true,
          },
        });

        return {
          ...user,
          paymentCount: user._count.payments,
          totalPaymentAmount: totalAmount._sum.amountTotal || 0,
        };
      })
    );

    return res.json({
      users: usersWithStats,
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

/**
 * GET /api/admin/users/:id
 * Get user details
 */
export async function getUserDetails(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const user = await prisma.user.findUnique({
      where: { id },
      select: {
        id: true,
        uid: true,
        createdAt: true,
        deletedAt: true,
        consentRecords: {
          orderBy: { createdAt: 'desc' },
        },
        payments: {
          take: 20,
          orderBy: { createdAt: 'desc' },
          select: {
            id: true,
            amountTotal: true,
            paymentStatus: true,
            paymentMethod: true,
            createdAt: true,
          },
        },
      },
    });

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Get total payment amount
    const totalAmount = await prisma.payment.aggregate({
      where: {
        userId: id,
        paymentStatus: 'PAID',
      },
      _sum: {
        amountTotal: true,
      },
    });

    // Audit log for viewing user details
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'VIEW_USER_DETAILS',
        entityType: 'User',
        entityId: id,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json({
      ...user,
      totalPaymentAmount: totalAmount._sum.amountTotal || 0,
    });
  } catch (error) {
    next(error);
  }
}
