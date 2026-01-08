<script setup lang="ts">
  import type { NavigationMenuItem } from '@nuxt/ui'
  
  const bottomNavItems: NavigationMenuItem[] = [
    {
      label: '利用規約',
      to: '/terms',
    },
    {
      label: 'プライバシーポリシー',
      to: '/policy',
    },
    {
      label: '運営者情報',
      to: '/operator',
    },
    {
      label: 'お問い合わせ',
      to: '/contact',
    }
  ]
</script>
  
<template>
  <UApp>
    <UHeader title="Seren Walk" />

    <UMain>
      <NuxtLayout>
        <NuxtPage />
      </NuxtLayout>
    </UMain>

    <UFooter>
      <template #left>
        <p class="text-muted text-sm">Copyright © {{ new Date().getFullYear() }}</p>
      </template>
      <template #right>
        <UNavigationMenu :items="bottomNavItems" variant="link" />
      </template>
    </UFooter>
  </UApp>
</template>
