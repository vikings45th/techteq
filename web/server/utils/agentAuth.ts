import { GoogleAuth } from "google-auth-library";

/**
 * Agent（Cloud Run IAM 認証）向けに ID Token 付きリクエストヘッダーを取得する。
 * targetAudience は Agent のベース URL（https://...run.app、パスなし）。
 */
export async function getAgentRequestHeaders(
  targetAudience: string
): Promise<Record<string, string>> {
  const auth = new GoogleAuth();
  const client = await auth.getIdTokenClient(targetAudience);
  const headers = await client.getRequestHeaders();
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries()) as Record<string, string>;
  }
  return headers as Record<string, string>;
}
