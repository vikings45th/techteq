<script setup lang="ts">
import type { SuggestedRoute, ChatMessage } from "~/types/route";
import { useQuickSearch } from "~/composables/states";

const geminiStatus = ref("ready");
const isModalOpen = ref(false);
const quickSearchState = useQuickSearch();

const messages = ref<ChatMessage[]>([]);
const suggestedRoute = ref<SuggestedRoute>({
  message: "頭を休ませる30分の散歩に出かける？",
  theme: "think",
  distance_km: 2,
});
const features = ref([
  {
    title: "どこを歩くか考えなくていい",
    icon: "i-lucide-route",
  },
  {
    title: "今の気分に合った散歩ができる",
    icon: "i-lucide-heart",
  },
  {
    title: "いつもと少し違う道を歩けることがある",
    icon: "i-lucide-compass",
  },
]);

const firstSuggest = async () => {
  messages.value = [
    {
      id: crypto.randomUUID(),
      role: "assistant",
      parts: [
        {
          type: "text",
          text: "今に合う道を探しています。",
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
    id: crypto.randomUUID(),
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
    id: crypto.randomUUID(),
    role: "user",
    parts: [
      {
        type: "text",
        text: "ちょっと違う気分",
      },
    ],
  });
  geminiStatus.value = "submitted";

  // 0.5秒待機
  await new Promise((resolve) => setTimeout(resolve, 500));

  messages.value.push({
    id: crypto.randomUUID(),
    role: "assistant",
    parts: [
      {
        type: "text",
        text: "別の道を探しています。",
      },
    ],
  });

  const res = await $fetch<SuggestedRoute>("/api/gemini", {
    method: "POST",
    body: {
      prevTheme: suggestedRoute.value.theme,
      prevDistance: suggestedRoute.value.distance_km,
      model: "gemini-2.5-flash",
    },
  });

  geminiStatus.value = "ready";

  suggestedRoute.value = res;

  messages.value.push({
    id: crypto.randomUUID(),
    role: "assistant",
    parts: [
      {
        type: "text",
        text: res.message,
      },
    ],
  });
};

const handleSearch = async () => {
  messages.value.push({
    id: crypto.randomUUID(),
    role: "user",
    parts: [
      {
        type: "text",
        text: "案内してもらう",
      },
    ],
  });

  geminiStatus.value = "submitted";

  quickSearchState.value = {
    quick_search: true,
    theme: suggestedRoute.value.theme,
    distance_km: suggestedRoute.value.distance_km,
  };

  // 0.5秒待機
  await new Promise((resolve) => setTimeout(resolve, 500));

  navigateTo("/app/search");
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
    description="あなたの気分に寄り添った散歩コースを提案します。"
    orientation="horizontal"
  >
    <template #title> 歩けた<br />それだけで今日は十分 </template>
    <img
      src="/img/heroimg.jpg"
      alt="App screenshot"
      class="rounded-lg shadow-2xl ring ring-default"
    />
  </UPageHero>
  <UPageCTA
    title="散歩を提案してもらう"
    description="チャットでいくつか答えるだけです。"
  >
    <UDrawer
      title="散歩提案チャット"
      description="いくつか答えるだけで散歩を提案"
      direction="bottom"
      handle-only
    >
      <UButton
        color="primary"
        icon="i-lucide-message-circle"
        size="xl"
        block
        @click="isModalOpen = true"
      />

      <template #content>
        <div class="h-[90vh] flex flex-col min-h-0">
          <UChatPalette>
            <div class="flex flex-col flex-1 min-h-0 overflow-y-auto">
              <UChatMessages
                should-auto-scroll
                :status="geminiStatus"
                :messages="messages"
                :assistant="{
                  avatar: {
                    icon: 'material-symbols-light:footprint',
                  },
                }"
                :ui="{
                  root: 'w-full flex flex-col gap-1 px-2.5 flex-none [&>article]:last-of-type:min-h-0',
                }"
              />
              <div
                v-if="geminiStatus === 'ready'"
                class="flex flex-wrap gap-2 m-4 justify-end flex-none"
              >
                <UButton
                  label="案内してもらう"
                  color="primary"
                  variant="outline"
                  class="rounded-full"
                  @click="handleSearch"
                />
                <UButton
                  label="ちょっと違う気分"
                  color="neutral"
                  variant="outline"
                  class="rounded-full"
                  @click="resuggest"
                />
              </div>
            </div>
          </UChatPalette>
        </div>
      </template>
    </UDrawer>
  </UPageCTA>
  <UPageSection
    title="散歩した方がいいと分かっている。でも疲れているとどこを歩くかを考えられない。"
    description="今の気分に沿った散歩ルートを一つだけ提案します。"
    :features="features"
  />
</template>
