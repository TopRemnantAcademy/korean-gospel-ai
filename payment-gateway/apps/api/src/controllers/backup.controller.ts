import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import logger from '../utils/logger';
import { env } from '../config/env';
import fs from 'fs';
import path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

const BACKUP_DIR = env.BACKUP_DIR || './backups';
const MAX_BACKUPS = 30; // Keep 30 days of backups

/**
 * GET /api/admin/backups
 * Get list of backups
 */
export async function getBackups(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    // Ensure backup directory exists
    if (!fs.existsSync(BACKUP_DIR)) {
      fs.mkdirSync(BACKUP_DIR, { recursive: true });
    }

    const files = fs.readdirSync(BACKUP_DIR);
    const backups = files
      .filter(file => file.endsWith('.sql'))
      .map(file => {
        const filePath = path.join(BACKUP_DIR, file);
        const stats = fs.statSync(filePath);
        return {
          filename: file,
          size: stats.size,
          createdAt: stats.birthtime,
        };
      })
      .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());

    return res.json({ backups });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/backups
 * Create a backup
 */
export async function createBackup(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    // Ensure backup directory exists
    if (!fs.existsSync(BACKUP_DIR)) {
      fs.mkdirSync(BACKUP_DIR, { recursive: true });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `backup-${timestamp}.sql`;
    const filepath = path.join(BACKUP_DIR, filename);

    // Get database connection info from environment
    const dbUrl = env.DATABASE_URL;
    if (!dbUrl) {
      return res.status(500).json({ error: 'DATABASE_URL not configured' });
    }

    // Parse database URL
    const url = new URL(dbUrl);
    const host = url.hostname;
    const port = url.port || '5432';
    const database = url.pathname.slice(1);
    const username = url.username;
    const password = url.password;

    // Create backup using pg_dump (execFile prevents shell injection)
    await execFileAsync('pg_dump', [
      '-h', host,
      '-p', port,
      '-U', username,
      '-d', database,
      '-F', 'p',
      '-f', filepath,
    ], {
      env: { ...process.env, PGPASSWORD: password },
    });

    // Get backup file stats
    const stats = fs.statSync(filepath);

    // Clean up old backups
    const files = fs.readdirSync(BACKUP_DIR)
      .filter(file => file.endsWith('.sql'))
      .map(file => ({
        filename: file,
        path: path.join(BACKUP_DIR, file),
        createdAt: fs.statSync(path.join(BACKUP_DIR, file)).birthtime,
      }))
      .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());

    // Delete old backups
    if (files.length > MAX_BACKUPS) {
      for (let i = MAX_BACKUPS; i < files.length; i++) {
        fs.unlinkSync(files[i].path);
        logger.info(`Deleted old backup: ${files[i].filename}`);
      }
    }

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'CREATE_BACKUP',
        entityType: 'Backup',
        entityId: filename,
        afterJson: {
          filename,
          size: stats.size,
        } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Backup created: ${filename} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      backup: {
        filename,
        size: stats.size,
        createdAt: new Date(),
      },
    });
  } catch (error) {
    logger.error('Backup creation failed:', (error as Error).message);
    next(error);
  }
}

/**
 * GET /api/admin/backups/:filename/download
 * Download a backup file
 */
export async function downloadBackup(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { filename } = req.params;

    // Security: Prevent directory traversal
    if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    const filepath = path.join(BACKUP_DIR, filename);

    if (!fs.existsSync(filepath)) {
      return res.status(404).json({ error: 'Backup not found' });
    }

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'DOWNLOAD_BACKUP',
        entityType: 'Backup',
        entityId: filename,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Backup downloaded: ${filename} by ${req.adminUser!.email}`);

    return res.download(filepath);
  } catch (error) {
    next(error);
  }
}

/**
 * DELETE /api/admin/backups/:filename
 * Delete a backup
 */
export async function deleteBackup(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { filename } = req.params;

    // Security: Prevent directory traversal
    if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    const filepath = path.join(BACKUP_DIR, filename);

    if (!fs.existsSync(filepath)) {
      return res.status(404).json({ error: 'Backup not found' });
    }

    fs.unlinkSync(filepath);

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'DELETE_BACKUP',
        entityType: 'Backup',
        entityId: filename,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Backup deleted: ${filename} by ${req.adminUser!.email}`);

    return res.json({ success: true, message: 'Backup deleted' });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/backups/:filename/restore
 * Restore from a backup (SUPER_ADMIN only)
 */
export async function restoreBackup(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { filename } = req.params;

    // Security: Prevent directory traversal
    if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    const filepath = path.join(BACKUP_DIR, filename);

    if (!fs.existsSync(filepath)) {
      return res.status(404).json({ error: 'Backup not found' });
    }

    // Get database connection info
    const dbUrl = env.DATABASE_URL;
    if (!dbUrl) {
      return res.status(500).json({ error: 'DATABASE_URL not configured' });
    }

    // Parse database URL
    const url = new URL(dbUrl);
    const host = url.hostname;
    const port = url.port || '5432';
    const database = url.pathname.slice(1);
    const username = url.username;
    const password = url.password;

    // Restore using psql (execFile prevents shell injection)
    await execFileAsync('psql', [
      '-h', host,
      '-p', port,
      '-U', username,
      '-d', database,
      '-f', filepath,
    ], {
      env: { ...process.env, PGPASSWORD: password },
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'RESTORE_BACKUP',
        entityType: 'Backup',
        entityId: filename,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Backup restored: ${filename} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      message: 'Backup restored successfully',
    });
  } catch (error) {
    logger.error('Backup restore failed:', (error as Error).message);
    next(error);
  }
}
