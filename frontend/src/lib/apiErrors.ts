import { ApiError } from "@/lib/apiTransport";

/** True when a request failed because the resource does not exist. */
export const isNotFound = (error: unknown): boolean =>
  error instanceof ApiError && error.status === 404;
