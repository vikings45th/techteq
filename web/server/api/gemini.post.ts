import { GoogleGenAI } from "@google/genai";
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

interface SuggestedRoute {
  message: string;
  theme: string;
  distance_km: number;
}

const suggestedRouteSchema = z.object({
  message: z.string().describe("ユーザーに提案するメッセージ（30文字程度）"),
  theme: z
    .enum(["think", "nature", "refresh", "exercise"])
    .describe("選択したモード名"),
  distance_km: z.number().min(1).max(3).describe("距離（1-3の数値、小数点可）"),
});

const createWalkingSuggestionPrompt = (
  currentDateTime: string,
  prevTheme?: string,
) => `現在の日本の状況（日時、天候、時間帯など）を考慮して、以下の4種類の散歩モードのうち最も適切な1つを選んでください。
${prevTheme ? `\n【重要】前回の提案テーマは「${prevTheme}」でした。今回の提案では、前回とは**別のテーマ**を必ず選んでください。\n` : ""}

現在の情報：
${currentDateTime}

各モードの説明：

🌫️ think（考えなくていい道モード）
「今日は、頭を休ませる道を用意しました。」
一本道が中心のコースです。考えなくてOK。歩くだけで大丈夫です。
メッセージ例：「頭を休ませる30分の散歩に出かける？」
距離：1-2km程度（歩行時間：約15-30分）
適したタイミング：疲れている時、頭を使った後、夜間など

🫧 nature（呼吸を整えるモード）
「呼吸が少し楽になる道です。」
空や木が見える場所を通ります。何かしなくていいので、ただ外の空気に触れてみませんか。
メッセージ例：「呼吸を整える20分の散歩に出かける？」
距離：1-2km程度（歩行時間：約15-30分）
適したタイミング：天気が良い時、日中、空気が澄んでいる時など

🌤️ refresh（ちょっと気分転換モード）
「景色を少しだけ変える散歩です。」
見るだけの場所がいくつかあります。寄らなくて大丈夫。通り過ぎるだけでOKです。
メッセージ例：「ちょっと気分転換の25分の散歩に出かける？」
距離：1-3km程度（歩行時間：約15-45分）
適したタイミング：午前中、午後、気分転換したい時など

🌅 exercise（体を使って整えるモード）
「少し体を動かすと、気持ちが変わることがあります。」
ゆるい坂があるコースです。途中でやめてもOK。行けたところまでで十分です。
メッセージ例：「体を使って整える40分の散歩に出かける？」
距離：2-3km程度（歩行時間：約30-45分）
適したタイミング：朝、午前中、体を動かしたい時など

現在の日時、時間帯、季節、天候の可能性などを考慮して、最も適切なモードを1つ選び、以下の形式で返してください：

messageフィールドには、ユーザーに提案するメッセージ（30文字程度）を文字列で指定してください。必ず歩行時間（何分程度）の情報を含めてください。距離から歩行時間を計算する際は、一般的な歩行速度（時速4-5km、つまり1kmあたり約12-15分）を基準にしてください。現在の時間帯や状況に合わせた自然な表現にしてください。
例：「頭を休ませる30分の散歩に出かける？」「呼吸を整える20分の散歩に出かける？」など
themeフィールドには、選択したモード名（think, nature, refresh, exercise のいずれか）を文字列で指定してください。
distance_kmフィールドには、距離（1から3の数値、小数点可）を数値で指定してください。この距離から歩行時間を計算して、messageに含めてください。

コードブロック記号（バッククォート3つなど）は使用せず、純粋なJSONオブジェクトのみを返してください。`;

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig();
  const apiKey = config.geminiApiKey;

  const body = await readBody(event);
  const { model = "gemini-2.5-flash", prevTheme } = body as {
    model?: string;
    prevTheme?: string;
  };

  // 現在の日本の日時情報を取得
  const now = new Date();
  const jstDate = new Date(
    now.toLocaleString("en-US", { timeZone: "Asia/Tokyo" }),
  );
  const currentDateTime = `現在の日時: ${jstDate.toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    weekday: "long",
  })} (JST)`;

  const ai = new GoogleGenAI({ apiKey });
  // @ts-ignore - zod-to-json-schema type compatibility issue
  const jsonSchema = zodToJsonSchema(suggestedRouteSchema);
  const prompt = createWalkingSuggestionPrompt(currentDateTime, prevTheme);
  const response = await ai.models.generateContent({
    model,
    contents: prompt,
    config: {
      responseMimeType: "application/json",
      responseJsonSchema: jsonSchema as any,
    },
  });

  const responseText = response.text;

  // 構造化出力により、JSONが保証されているので直接パース
  try {
    const parsed = suggestedRouteSchema.parse(
      JSON.parse(responseText!),
    ) as SuggestedRoute;
    return parsed;
  } catch (error) {
    console.error("Failed to parse JSON response:", error);
    throw createError({
      statusCode: 500,
      statusMessage: "Failed to parse AI response",
    });
  }
});
