import { getAgentRequestHeaders } from "../utils/agentAuth";

interface RouteFeedbackRequest {
  request_id: string;
  route_id: string;
  rating: number;
}

interface AgentFeedbackResponse {
  request_id: string;
  status: string;
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig();
  const agentBaseUrl = config.agentBaseUrl as string | undefined;
  if (!agentBaseUrl) {
    throw createError({
      statusCode: 500,
      statusMessage: "AGENT_BASE_URL is not configured",
    });
  }

  const requestBody = await readBody<RouteFeedbackRequest>(event);
  const apiUrl = `${agentBaseUrl}/route/feedback`;

  try {
    const idTokenHeaders = await getAgentRequestHeaders(agentBaseUrl);
    const response: AgentFeedbackResponse = await $fetch(apiUrl, {
      method: "POST",
      headers: {
        ...idTokenHeaders,
        "Content-Type": "application/json",
      },
      body: requestBody,
    });

    return {
      statusCode: 200,
      body: response,
    };
  } catch (error: any) {
    const status = error?.statusCode ?? error?.response?.status ?? 500;
    if (status === 401 || status === 403) {
      console.error(
        "Agent IAM auth failed (audience/権限不足の可能性):",
        agentBaseUrl,
        status
      );
    }
    throw createError({
      statusCode: status,
      statusMessage: error.message || "フィードバック送信に失敗しました",
    });
  }
});
