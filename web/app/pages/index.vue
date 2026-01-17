<script setup lang="ts">
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
		<UButton label="詳細条件を入力" variant="outline" to="/app/search"/>
	</UPageSection>
	<UPageSection
    title="“ちょうどいい散歩コース”を提案します"
    description="気分を選ぶだけ"
		:features="features"
  />
	<UPageCTA
		title="考えなくていい散歩、試してみる"
		:links="ctaLinks"
	/>
</template>