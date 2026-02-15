import { GoogleAuth } from "google-auth-library";

export async function getAgentAuthHeaders(
  agentBaseUrl: string,
): Promise<Record<string, string>> {
  const auth = new GoogleAuth();
  const client = await auth.getIdTokenClient(agentBaseUrl);
  const headers = await client.getRequestHeaders();

  return headers;
}
