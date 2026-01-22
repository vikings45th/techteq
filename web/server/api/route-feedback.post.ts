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
  const requestBody = await readBody<RouteFeedbackRequest>(event);

  const apiUrl = "https://agent-203786374782.asia-northeast1.run.app/route/feedback";
  
  try {
    const response: AgentFeedbackResponse = await $fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: requestBody
    });
    
    return {
      statusCode: 200,
      body: response
    };
    
  } catch (error: any) {
    throw createError({
      statusCode: error.statusCode || 500,
      statusMessage: error.message || 'フィードバック送信に失敗しました'
    });
  }
})
