<script setup lang="ts">
	const generateParams = ref("/app?theme=exercise&distance=5");

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
			to: '/app',
			icon: 'i-lucide-square-play'
		},
	])

	const handleSubmit = (m: string, d: number) => {
		generateParams.value = "/app?theme="+m+"&distance="+d;
	};

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
		<RouteForm :detailed="false" @submit="handleSubmit"/>
		<UButton label="ルート生成" :to="generateParams"/>
		<UButton label="詳細条件を入力" variant="outline" to="/app"/>
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