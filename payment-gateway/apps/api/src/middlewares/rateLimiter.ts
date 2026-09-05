import rateLimit from 'express-rate-limit';
import { 
  RATE_LIMIT_WINDOW_15_MIN, 
  RATE_LIMIT_WINDOW_1_HOUR, 
  RATE_LIMIT_WINDOW_1_MIN 
} from '../constants/time';

export const publicApiLimiter = rateLimit({
  windowMs: RATE_LIMIT_WINDOW_15_MIN,
  max: 100, // limit each IP to 100 requests per windowMs
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: 'Too many requests from this IP, please try again after 15 minutes',
  },
});

export const authLimiter = rateLimit({
  windowMs: RATE_LIMIT_WINDOW_15_MIN,
  max: 10, // Reduced from 20 to 10 for better security
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: 'Too many authentication attempts, please try again after 15 minutes',
  },
});

export const paymentLimiter = rateLimit({
  windowMs: RATE_LIMIT_WINDOW_1_MIN,
  max: 5, // Reduced from 10 to 5 for better security
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: 'Too many checkout requests, please wait before trying again',
  },
});

// New: Strict rate limiter for sensitive operations
export const strictLimiter = rateLimit({
  windowMs: RATE_LIMIT_WINDOW_1_HOUR,
  max: 3, // Only 3 attempts per hour
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: 'Too many attempts, please try again after 1 hour',
  },
});
