<script setup lang="ts">
  const themeItems = ref([{
    label: '体を動かしたい',
    value: 'exercise'
  }, {
    label: '考え事をしたい',
    value: 'think'
  }, {
    label: 'リフレッシュしたい',
    value: 'refresh'
  }, {
    label: '自然を感じたい',
    value: 'nature'
  }]);
	const theme = ref("exercise");

	const features = ref([
		{
			title: '今の気分',
			icon: 'i-lucide-smile',
		},
		{
			title: '使える時間',
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
  >
		<div>
			<URadioGroup 
				indicator="hidden" 
				v-model="theme" 
				:items="themeItems" 
				variant="card" 
				class="mb-2"
				:ui="{
					fieldset: 'grid grid-cols-2 gap-2 mb-2'
				}"
			/>
			<UButton block label="散歩ルートを検索" color="secondary" :to="`/app/search?theme=${theme}&quicksearch=true`" class="text-lg mb-2 font-bold rounded-full"/>
			<UButton block label="詳細条件を入力" variant="link" to="/app/search" class="rounded-full"/>
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