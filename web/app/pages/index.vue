<script setup lang="ts">
  const themeItems = ref([{
    label: '体を動かしたい',
    value: 'exercise',
    icon: 'i-lucide-activity'
  }, {
    label: '考え事をしたい',
    value: 'think',
    icon: 'i-lucide-brain'
  }, {
    label: 'リフレッシュしたい',
    value: 'refresh',
    icon: 'i-lucide-sparkles'
  }, {
    label: '自然を感じたい',
    value: 'nature',
    icon: 'i-lucide-trees'
  }]);
	const theme = ref("exercise");

	const features = ref([
		{
			title: '気分',
			icon: 'i-lucide-smile',
		},
		{
			title: 'やる気',
			icon: 'i-lucide-a-large-small',
		},
		{
			title: '出発地点',
			icon: 'i-lucide-sun-moon',
		}
	])

	const ctaLinks = ref([
		{
			label: '散歩する',
			to: '/app/search',
			icon: 'i-lucide-square-play'
		},
	])
</script>

<template>
	<UPageHero
		title="Seren Walk"
		description="気分に合わせて「少しだけ新しい散歩ルート」が見つかる"
		orientation="horizontal"
	>
		<img
      src="/img/heroimg.jpg"
      alt="App screenshot"
      class="rounded-lg shadow-2xl ring ring-default"
    />
	</UPageHero>
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
        >
          <template #label="{ item }">
            <div class="flex items-center gap-2">
              <UIcon v-if="item.icon" :name="item.icon" class="w-4 h-4" />
              <span>{{ item.label }}</span>
            </div>
          </template>
        </URadioGroup>
      </div>
			<UButton block label="散歩ルートを検索" color="secondary" :to="`/app/search?theme=${theme}&quicksearch=true`" class="text-lg mb-2 font-bold rounded-full"/>
			<UButton block label="詳細条件を入力" color="secondary" variant="link" to="/app/search" class="rounded-full"/>
		</div>
	</UPageSection>
	<UPageSection
    title="“ちょうどいい散歩コース”を提案します"
		:features="features"
  />
	<UPageCTA
		title="考えなくていい散歩、試してみる"
		:links="ctaLinks"
	/>
</template>

<style scoped>
	.scrollbar-hide {
		-ms-overflow-style: none;  /* IE and Edge */
		scrollbar-width: none;  /* Firefox */
	}
	
	.scrollbar-hide::-webkit-scrollbar {
		display: none;  /* Chrome, Safari and Opera */
	}
</style>