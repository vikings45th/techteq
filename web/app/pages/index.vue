<script setup lang="ts">
type ChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  parts: { type: string; text: string }[];
};

const messages = ref<ChatMessage[]>([]);
const suggestedRoute = {
  message: "頭を休ませる30分の散歩に出かける？",
  theme: "think",
  distanve_km: 2,
};
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
  const { text } = await $fetch<{ text: string }>("/api/gemini", {
    method: "POST",
    body: {
      contents: "Explain how AI works in a few words",
      model: "gemini-2.5-flash",
    },
  });
  messages.value.push({
    id: "6045235a-a435-46b8-989d-2df38ca2eb47",
    role: "assistant",
    parts: [
      {
        type: "text",
        text: text,
      },
    ],
  });
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
    <UChatMessages :messages="messages" />
    <div class="flex flex-wrap gap-2">
      <UButton
        v-for="(label, index) in chatButtonLabels"
        :key="index"
        :label="label"
        color="neutral"
        variant="soft"
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
