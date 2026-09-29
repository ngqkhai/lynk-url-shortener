export class AppError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}

export class NotFoundError extends AppError {
  constructor() {
    super(404, 'NOT_FOUND', 'Short URL not found');
  }
}

export class ExpiredError extends AppError {
  constructor() {
    super(410, 'URL_EXPIRED', 'Short URL has expired');
  }
}

export class DependencyUnavailableError extends AppError {
  constructor(message = 'URL source is temporarily unavailable') {
    super(503, 'DEPENDENCY_UNAVAILABLE', message);
  }
}
