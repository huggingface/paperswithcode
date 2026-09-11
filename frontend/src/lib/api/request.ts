import { withStaleAuthNotification } from "../apiAuth";
import { ApiTransport, type ApiRequest } from "../apiTransport";
import { getApiOrigin } from "../apiUrl";

const apiTransport = new ApiTransport(`${getApiOrigin()}/api/v1`);

export const apiFetch = (endpoint: string, options?: RequestInit): Promise<Response> =>
  apiTransport.fetch(endpoint, options);

export const apiRequest: ApiRequest = <T>(
  endpoint: string,
  options?: RequestInit,
) => withStaleAuthNotification(() => apiTransport.request<T>(endpoint, options));
