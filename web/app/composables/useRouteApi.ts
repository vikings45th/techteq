import type { ApiRequest, ApiResponse, RouteFeedbackRequest, RouteFeedbackResponse } from '~/types/route';

interface RouteFeedbackApiResponse {
  statusCode: number;
  body: RouteFeedbackResponse;
}

export const useRouteApi = () => {
  const fetchRoute = async (payload: ApiRequest): Promise<ApiResponse['body']['route']> => {
    const response = await $fetch<ApiResponse>("/api/fetch-ai", {
      method: "post",
      body: payload,
    });
    return response.body.route;
  };

  const submitRouteFeedback = async (payload: RouteFeedbackRequest): Promise<RouteFeedbackResponse> => {
    const response = await $fetch<RouteFeedbackApiResponse>("/api/route-feedback", {
      method: "post",
      body: payload,
    });
    return response.body;
  };

  return { fetchRoute, submitRouteFeedback };
};
