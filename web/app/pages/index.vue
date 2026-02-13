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

const ctaLinks = ref([
  {
    label: "散歩する",
    to: "/app/search",
    icon: "i-lucide-square-play",
  },
]);

const chatButtonLabels = ref([
  "これで行く",
  "もうちょっと長く",
  "もうちょっと短く",
]);

const firstSuggest = async () => {
  messages.value = [
    {
      id: "6045235a-a435-46b8-989d-2df38ca2eb47",
      role: "assistant",
      parts: [
        {
          type: "text",
          text: "あなたにおすすめの散歩ルートを考えています",
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

const handleButtonClick = (label: string) => {
  if (label === "これで行く") {
    navigateTo(
      `/app/search?theme=${suggestedRoute.value.theme}&distance_km=${suggestedRoute.value.distance_km}&quicksearch=true`,
    );
  } else if (label === "もうちょっと長く") {
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
  } else if (label === "もうちょっと短く") {
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

onMounted(async () => {
  //await firstSuggest();
});
</script>

<template>
  <UPageHero
    title="今の気分に、ちょうどいい道。"
    description="気分に合わせて「少しだけ新しい散歩ルート」が見つかる"
    orientation="horizontal"
  >
    <img
      src="/img/heroimg.jpg"
      alt="App screenshot"
      class="rounded-lg shadow-2xl ring ring-default"
    />
  </UPageHero>
  <!--
	<UPageSection
    title="早速歩く"
		description="今どんな気分？"
  >
		<div>

      <div class="overflow-x-auto pb-4 mr-2 px-2 scrollbar-hide">
        <URadioGroup 
          indicator="hidden"
          orientation="horizontal"
          v-model="theme" 
          :items="themeItems" 
          variant="card"
          :ui="{
            wrapper: 'shrink-0 whitespace-nowrap w-auto',  
          }"
        />
      </div>
			<UButton block label="散歩ルートを検索" color="secondary" :to="`/app/search?theme=${theme}&quicksearch=true`" class="text-lg mb-2 font-bold rounded-full"/>
			<UButton block label="詳細条件を入力" color="secondary" variant="link" to="/app/search" class="rounded-full"/>
		</div>
	</UPageSection>
				-->
  <UPageSection title="早速歩く">
    <UButton @click="firstSuggest">CallGemini</UButton>
    <UChatMessages
      :status="geminiStatus"
      :messages="messages"
      :assistant="{
        avatar: {
          src: 'https://github.com/benjamincanac.png',
        },
      }"
    />
    <div class="flex flex-wrap gap-2">
      <UButton
        v-for="(label, index) in chatButtonLabels"
        :key="index"
        :label="label"
        color="neutral"
        variant="outline"
        @click="handleButtonClick(label)"
      />
    </div>
  </UPageSection>

  <UPageSection
    title="散歩はやったほうがいいと分かっている。でも、疲れていると「どこを歩くか」を考えられない。"
    description="このアプリは、今の気分に沿った散歩ルートを一つだけ提案します。"
    :features="features"
  />
  <UPageCTA
    title="考えなくていい。今の気分のまま、外に出られる。"
    :links="ctaLinks"
  />
</template>

<style scoped>
.scrollbar-hide {
  -ms-overflow-style: none; /* IE and Edge */
  scrollbar-width: none; /* Firefox */
}

.scrollbar-hide::-webkit-scrollbar {
  display: none; /* Chrome, Safari and Opera */
}
</style>
