<script setup>
  definePageMeta({
    layout: 'app',
  })
</script>
<template>
  <h1 class="mb-4">目的と距離に合わせてルートを提案します</h1>
  <RouteForm :detailed="true" :theme="$route.query.theme" :distance="Number($route.query.distance ?? 5)"/>
</template>