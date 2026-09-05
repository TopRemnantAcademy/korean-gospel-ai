/**
 * Time-related constants to avoid magic numbers throughout the codebase
 */

// Milliseconds
export const MS_PER_SECOND = 1000;
export const MS_PER_MINUTE = 60 * MS_PER_SECOND;
export const MS_PER_HOUR = 60 * MS_PER_MINUTE;
export const MS_PER_DAY = 24 * MS_PER_HOUR;

// Common durations in milliseconds
export const THIRTY_MINUTES_MS = 30 * MS_PER_MINUTE;
export const FIFTEEN_MINUTES_MS = 15 * MS_PER_MINUTE;
export const ONE_HOUR_MS = MS_PER_HOUR;
export const ONE_DAY_MS = MS_PER_DAY;
export const SEVEN_DAYS_MS = 7 * MS_PER_DAY;

// Rate limiting windows
export const RATE_LIMIT_WINDOW_15_MIN = FIFTEEN_MINUTES_MS;
export const RATE_LIMIT_WINDOW_1_HOUR = ONE_HOUR_MS;
export const RATE_LIMIT_WINDOW_1_MIN = MS_PER_MINUTE;

// Payment order expiry
export const PAYMENT_ORDER_EXPIRY_MS = THIRTY_MINUTES_MS;

// SSO token expiry
export const SSO_TOKEN_EXPIRY_SECONDS = 60;

// Background job delays
export const JOB_INITIAL_DELAY_MS = 5000; // 5 seconds
export const JOB_MAX_DELAY_MS = 80 * MS_PER_SECOND; // 80 seconds (exponential backoff max)

// Polling intervals
export const STATUS_POLLING_INTERVAL_MS = 4000; // 4 seconds
export const STATUS_POLLING_MAX_INTERVAL_MS = 30000; // 30 seconds (max with backoff)
