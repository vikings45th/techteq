import { GoogleGenAI } from "@google/genai";

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig();
  const apiKey = config.geminiApiKey;

  if (!apiKey) {
    throw createError({
      statusCode: 500,
      statusMessage: "Gemini API key is not configured",
    });
  }

  const body = await readBody(event);
  const {
    contents = "Explain how AI works in a few words",
    model = "gemini-2.5-flash",
  } = body as {
    contents?: string;
    model?: string;
  };

  const ai = new GoogleGenAI({ apiKey });
  const response = await ai.models.generateContent({
    model,
    contents,
  });
  console.log(response);

  return { text: response.text };
});
