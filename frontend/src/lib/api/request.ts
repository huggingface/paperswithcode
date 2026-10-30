import { withStaleAuthNotification } from "../apiAuth";
import { ApiError, ApiTransport, type ApiRequest } from "../apiTransport";
import { getApiOrigin } from "../apiUrl";

const apiTransport = new ApiTransport(`${getApiOrigin()}/api/v1`);

export const apiFetch = (endpoint: string, options?: RequestInit): Promise<Response> =>
  apiTransport.fetch(endpoint, options);

/** The raw response of a successful request; failures reject with `ApiError`. */
export const apiResponse = (endpoint: string, options?: RequestInit): Promise<Response> =>
  withStaleAuthNotification(() => apiTransport.fetchOk(endpoint, options));

export const apiRequest: ApiRequest = <T>(
  endpoint: string,
  options?: RequestInit,
) => withStaleAuthNotification(() => apiTransport.request<T>(endpoint, options));

/** Like `apiRequest`, but resolves to null when the resource does not exist. */
export async function apiRequestOrNull<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T | null> {
  try {
    return await apiRequest<T>(endpoint, options);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
