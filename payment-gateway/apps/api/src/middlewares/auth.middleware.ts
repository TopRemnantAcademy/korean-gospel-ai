import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { env } from '../config/env';
import prisma from '../repositories/db';
import { AdminRole } from '@gospel-pay/shared';

export interface AuthenticatedAdminRequest extends Request {
  adminUser?: {
    id: string;
    email: string;
    role: AdminRole;
  };
}

export async function adminAuthRequired(
  req: AuthenticatedAdminRequest,
  res: Response,
  next: NextFunction
) {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'Unauthorized: Missing or invalid authentication token' });
    }

    const token = authHeader.split(' ')[1];
    const decoded = jwt.verify(token, env.JWT_SECRET, { algorithms: ['HS256'] }) as {
      id: string;
      email: string;
      role: AdminRole;
    };

    const admin = await prisma.adminUser.findUnique({
      where: { id: decoded.id },
    });

    if (!admin || !admin.isActive) {
      return res.status(401).json({ error: 'Unauthorized: Admin user account is inactive or deleted' });
    }

    req.adminUser = {
      id: admin.id,
      email: admin.email,
      role: admin.role as AdminRole,
    };

    next();
  } catch (error: any) {
    return res.status(401).json({ error: 'Unauthorized: Token verification failed', details: error.message });
  }
}

export function roleRequired(allowedRoles: AdminRole[]) {
  return (req: AuthenticatedAdminRequest, res: Response, next: NextFunction) => {
    if (!req.adminUser) {
      return res.status(401).json({ error: 'Unauthorized: Authentication required' });
    }

    const hasRole = allowedRoles.includes(req.adminUser.role);
    if (!hasRole) {
      return res.status(403).json({ 
        error: `Forbidden: Access restricted. Required roles: [${allowedRoles.join(', ')}]. Current role: ${req.adminUser.role}` 
      });
    }

    next();
  };
}

// Alias for cleaner route imports
export const requireAdminAuth = adminAuthRequired;

export function requireSuperAdmin(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  if (!req.adminUser) {
    return res.status(401).json({ error: 'Unauthorized: Authentication required' });
  }

  if (req.adminUser.role !== AdminRole.SUPER_ADMIN) {
    return res.status(403).json({ error: 'Forbidden: SUPER_ADMIN access required' });
  }

  next();
}
