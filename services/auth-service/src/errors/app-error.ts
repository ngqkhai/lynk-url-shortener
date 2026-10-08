export class AppError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}
export class UnauthorizedError extends AppError {
  constructor() {
    super(401, 'UNAUTHORIZED', 'Invalid credentials or token');
  }
}
export class EmailConflictError extends AppError {
  constructor() {
    super(409, 'EMAIL_CONFLICT', 'Email is already registered');
  }
}
export class UnavailableError extends AppError {
  constructor() {
    super(503, 'AUTH_UNAVAILABLE', 'Authentication temporarily unavailable');
  }
}
