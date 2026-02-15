// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  devtools: { enabled: true },
  modules: ["@nuxt/ui"],
  css: ["~/assets/css/main.css"],
  runtimeConfig: {
    geminiApiKey: process.env.NUXT_GEMINI_API_KEY,
    agentBaseUrl: process.env.NUXT_AGENT_BASE_URL,
    public: {
      googleMapsApiKey: process.env.NUXT_PUBLIC_GOOGLE_MAPS_API_KEY,
    },
  },
  vue: {
    compilerOptions: {
      isCustomElement: (tag) => tag.startsWith("gmp-"),
    },
  },
});
