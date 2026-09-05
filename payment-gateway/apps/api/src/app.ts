import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import crypto from 'crypto';
import authRouter from './routes/auth.routes';
import paymentRouter from './routes/payment.routes';
import adminRouter from './routes/admin.routes';
import paymentGatewayRouter from './routes/paymentGateway.routes';
import { errorHandler } from './middlewares/error.middleware';
import { healthCheckHandler } from './utils/healthCheck';
import { env } from './config/env';

const app = express();

app.set('trust proxy', true);

// Request ID Tracing Middleware
app.use((req, res, next) => {
  const reqId = req.headers['x-request-id'] || crypto.randomUUID();
  req.headers['x-request-id'] = reqId;
  res.setHeader('x-request-id', reqId);
  next();
});

// Security & Cross-Origin
app.use(helmet());
app.use(
  cors({
    origin: env.CORS_ORIGINS,
    credentials: true,
  })
);

// Body Parsers with size limits to prevent DoS attacks
app.use(express.json({ limit: '10kb' }));
app.use(express.urlencoded({ extended: true, limit: '10kb' }));

// Health Check (detailed)
app.get('/health', healthCheckHandler);

// Simple health check for load balancers
app.get('/ping', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// API Routes
app.use('/api', authRouter);
app.use('/api', paymentRouter);
app.use('/api', adminRouter);
app.use('/api/admin', paymentGatewayRouter);

// Global Error Handler
app.use(errorHandler as any);

export default app;
