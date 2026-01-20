/**
 * request_id(UUID)生成用のcomposable
 */
export const useGenerateRequestid = () => {
  const generateRequestid = (): string => {
    return typeof crypto !== 'undefined' && crypto.randomUUID 
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).substring(2)}`;
  };

  return { generateRequestid };
};