<script setup lang="ts">
import type { NavigationMenuItem } from "@nuxt/ui";

const bottomNavItems: NavigationMenuItem[] = [
  {
    label: "利用規約",
    to: "/terms",
  },
  {
    label: "ポリシー",
    to: "/policy",
  },
  {
    label: "運営者情報",
    to: "/operator",
  },
  {
    label: "お問い合わせ",
    to: "/contact",
  },
];
</script>

<template>
  <UHeader title="てくてく" :toggle="false" />
  <UMain>
    <UContainer>
      <slot />
    </UContainer>
  </UMain>
  <UFooter>
    <template #left>
      <p class="text-muted text-sm">
        Copyright © {{ new Date().getFullYear() }}
      </p>
    </template>
    <UNavigationMenu :items="bottomNavItems" variant="link" />
  </UFooter>
</template>
