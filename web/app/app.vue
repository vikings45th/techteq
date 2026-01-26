<script setup lang="ts">
  const runtimeConfig = useRuntimeConfig()
  // Dynamic Library Importを使用してGoogle Maps APIを読み込む
  useHead({
    script: [
      {
        src: `https://maps.googleapis.com/maps/api/js?key=${runtimeConfig.public.googleMapsApiKey}&libraries=maps,marker&v=weekly`,
        defer: true,
        key: 'google-maps-api' // 重複を防ぐためのキー
      }
    ]
  })
</script>

<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
