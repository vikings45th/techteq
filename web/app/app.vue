<script setup lang="ts">
const runtimeConfig = useRuntimeConfig();
// Dynamic Library Importを使用してGoogle Maps APIを読み込む
useHead({
  htmlAttrs: {
    lang: "ja",
  },
  title: "てくてく | 今の気分に合う散歩ルートを一つだけ提案",
  meta: [
    { name: "viewport", content: "width=device-width, initial-scale=1" },
    {
      name: "description",
      content:
        "チャットでいくつか答えるだけであなたの気分に寄り添った散歩コースを提案します",
    },
  ],
  script: [
    {
      src: `https://maps.googleapis.com/maps/api/js?key=${runtimeConfig.public.googleMapsApiKey}&libraries=maps,marker&v=weekly`,
      defer: true,
      key: "google-maps-api", // 重複を防ぐためのキー
    },
  ],
});
</script>

<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
