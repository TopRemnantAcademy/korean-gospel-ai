import { Request, Response, NextFunction } from 'express';
import logger from '../utils/logger';
import { env } from '../config/env';

export function errorHandler(
  err: any,
  req: Request,
  res: Response,
  next: NextFunction
) {
  const status = err.status || err.statusCode || 500;
  const requestId = req.headers['x-request-id'] || 'N/A';

  // Log error stack trace internally
  logger.error({
    message: err.message,
    stack: err.stack,
    requestId,
    path: req.path,
    method: req.method,
  });

  // Never expose stack trace to client-side in production
  const response: any = {
    error: err.message || 'Internal Server Error',
    requestId,
  };

  if (env.NODE_ENV === 'development') {
    response.stack = err.stack;
  }

  return res.status(status).json(response);
}

export default errorHandler;
