/** Error envelope (tech spec 0.6). Kept apart from api.ts so the mock can import it without a cycle. */

export interface ErrorEnvelope {
  error: { code: string; message: string; speech: string; retryable: boolean };
}

export class ApiError extends Error {
  code: string;
  speech: string;
  retryable: boolean;
  constructor(env: ErrorEnvelope['error']) {
    super(env.message);
    this.code = env.code;
    this.speech = env.speech;
    this.retryable = env.retryable;
  }
}
