<script setup lang="ts">
type ChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  parts: { type: string; text: string }[];
};

interface SuggestedRoute {
  message: string;
  theme: string;
  distance_km: number;
}

const geminiStatus = ref("ready");
const isModalOpen = ref(false);

const messages = ref<ChatMessage[]>([]);
const suggestedRoute = ref<SuggestedRoute>({
  message: "頭を休ませる30分の散歩に出かける？",
  theme: "think",
  distance_km: 2,
});
const features = ref([
  {
    title: "どこを歩くか考えなくていい",
    icon: "i-lucide-smile",
  },
  {
    title: "今の気分に合った散歩ができる",
    icon: "i-lucide-a-large-small",
  },
  {
    title: "いつもと少し違う道を歩けることがある",
    icon: "i-lucide-sun-moon",
  },
]);

const chatButtonLabels = ref([
  "これで行く",
  "ちょっと違う気分",
  "もう少し歩きたい",
  "少し短めがいい",
]);

const firstSuggest = async () => {
  messages.value = [
    {
      id: "6045235a-a435-46b8-989d-2df38ca2eb47",
      role: "assistant",
      parts: [
        {
          type: "text",
          text: "あなたにおすすめの散歩テーマを提案します。",
        },
      ],
    },
  ];
  geminiStatus.value = "submitted";
  const route = await $fetch<SuggestedRoute>("/api/gemini", {
    method: "POST",
    body: {
      model: "gemini-2.5-flash",
    },
  });

  geminiStatus.value = "ready";

  suggestedRoute.value = route;

  messages.value.push({
    id: "6045235a-a435-46b8-989d-2df38ca2eb47",
    role: "assistant",
    parts: [
      {
        type: "text",
        text: route.message,
      },
    ],
  });
};

const resuggest = async () => {
  messages.value.push({
    id: "6045235a-a435-46b8-989d-2df38ca2eb47",
    role: "assistant",
    parts: [
      {
        type: "text",
        text: "違う気分のテーマを考えています。",
      },
    ],
  });
  geminiStatus.value = "submitted";
  const route = await $fetch<SuggestedRoute>("/api/gemini", {
    method: "POST",
    body: {
      prevTheme: suggestedRoute.value.theme,
      model: "gemini-2.5-flash",
    },
  });

  geminiStatus.value = "ready";

  suggestedRoute.value = route;

  messages.value.push({
    id: "6045235a-a435-46b8-989d-2df38ca2eb47",
    role: "assistant",
    parts: [
      {
        type: "text",
        text: route.message,
      },
    ],
  });
};

const handleButtonClick = (label: string) => {
  messages.value.push({
    id: "6045235a-a435-46b8-989d-2df38ca2eb47",
    role: "user",
    parts: [
      {
        type: "text",
        text: label,
      },
    ],
  });

  if (label === "これで行く") {
    navigateTo(
      `/app/search?theme=${suggestedRoute.value.theme}&distance_km=${suggestedRoute.value.distance_km}&quicksearch=true`,
    );
  } else if (label === "ちょっと違う気分") {
    resuggest();
  } else if (label === "もう少し歩きたい") {
    // 距離を少し増やす処理（最大3kmまで）
    if (suggestedRoute.value.distance_km < 3) {
      suggestedRoute.value.distance_km = Math.min(
        suggestedRoute.value.distance_km + 0.5,
        3,
      );
      navigateTo(
        `/app/search?theme=${suggestedRoute.value.theme}&distance_km=${suggestedRoute.value.distance_km}&quicksearch=true`,
      );
    }
  } else if (label === "少し短めがいい") {
    // 距離を少し減らす処理（最小1kmまで）
    if (suggestedRoute.value.distance_km > 1) {
      suggestedRoute.value.distance_km = Math.max(
        suggestedRoute.value.distance_km - 0.5,
        1,
      );
      navigateTo(
        `/app/search?theme=${suggestedRoute.value.theme}&distance_km=${suggestedRoute.value.distance_km}&quicksearch=true`,
      );
    }
  }
};

// モーダルが開いたときに自動的に提案を取得
watch(isModalOpen, (newValue) => {
  if (newValue && messages.value.length === 0) {
    firstSuggest();
  }
});
</script>

<template>
  <UPageHero
    title="歩けた。それだけで今日は十分"
    description="あなたの気分に寄り添った散歩コースを提案します。"
    orientation="horizontal"
  >
    <img
      src="/img/heroimg.jpg"
      alt="App screenshot"
      class="rounded-lg shadow-2xl ring ring-default"
    />
  </UPageHero>
  <UPageSection
    title="散歩した方がいいと分かっている。でも、疲れていると「どこを歩くか」を考えられない。"
    description="このアプリは、今の気分に沿った散歩ルートを一つだけ提案します。"
    :features="features"
  />
  <UPageCTA title="考えなくていい。今の気分のまま、外に出られる。">
    <UButton
      color="secondary"
      label="ルートを教えてもらう"
      icon="mdi:walk"
      size="xl"
      block
      @click="isModalOpen = true"
    />
  </UPageCTA>

  <!-- フローティングアクションボタン -->
  <UButton
    v-if="!isModalOpen"
    icon="mdi:walk"
    color="secondary"
    size="xl"
    class="fixed bottom-6 right-6 rounded-full shadow-lg z-50 p-4"
    @click="isModalOpen = true"
  />
  <!-- モーダル -->
  <div
    v-if="isModalOpen"
    class="fixed bottom-6 right-6 w-[75vw] h-[50vh] p-4 shadow-lg border rounded-lg z-100 flex flex-col bg-neutral-50 dark:bg-neutral-600"
  >
    <div class="flex justify-end flex-shrink-0 mb-2">
      <UButton
        icon="i-lucide-x"
        color="neutral"
        size="xl"
        variant="outline"
        @click="isModalOpen = false"
        class="rounded-full"
      />
    </div>
    <div class="flex-1 overflow-y-auto min-h-0">
      <UChatPalette>
        <UChatMessages
          :status="geminiStatus"
          :messages="messages"
          :assistant="{
            avatar: {
              icon: 'i-lucide-bot',
            },
          }"
        />
        <div
          v-if="geminiStatus === 'ready'"
          class="flex flex-wrap gap-2 mt-4 justify-end"
        >
          <UButton
            v-for="(label, index) in chatButtonLabels"
            :key="index"
            :label="label"
            :color="index === 0 ? 'secondary' : 'neutral'"
            variant="outline"
            class="rounded-full"
            @click="handleButtonClick(label)"
          />
        </div>
      </UChatPalette>
    </div>
  </div>
</template>
