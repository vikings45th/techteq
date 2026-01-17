import type { ApiRequest, ApiResponse } from '~/types/route';

export const useRouteApi = () => {
  const fetchRoute = async (payload: ApiRequest): Promise<ApiResponse['body']['route']> => {
    const response = await $fetch<ApiResponse>("/api/fetch-ai", {
      method: "post",
      body: payload,
    });
    return response.body.route;
  };

  return { fetchRoute };
};
