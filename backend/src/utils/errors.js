/**
 * Application error hierarchy.
 * Controllers throw these; the global error handler catches and formats them.
 * This keeps HTTP status codes out of service/repository layers.
 */

class AppError extends Error {
  constructor(message, statusCode, code) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.isOperational = true;
    Error.captureStackTrace(this, this.constructor);
  }
}

class BadRequestError extends AppError {
  constructor(message = 'Bad request') {
    super(message, 400, 'BAD_REQUEST');
  }
}

class UnauthorisedError extends AppError {
  constructor(message = 'Authentication required') {
    super(message, 401, 'UNAUTHORISED');
  }
}

class ForbiddenError extends AppError {
  constructor(message = 'Access denied') {
    super(message, 403, 'FORBIDDEN');
  }
}

class NotFoundError extends AppError {
  constructor(message = 'Resource not found') {
    super(message, 404, 'NOT_FOUND');
  }
}

class ConflictError extends AppError {
  constructor(message = 'Resource already exists') {
    super(message, 409, 'CONFLICT');
  }
}

module.exports = {
  AppError,
  BadRequestError,
  UnauthorisedError,
  ForbiddenError,
  NotFoundError,
  ConflictError,
};
