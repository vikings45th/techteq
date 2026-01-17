import 'nuxt/app'

declare module 'nuxt/app' {
  interface NuxtLayouts {
    'default': unknown
    'app': unknown
  }
  type LayoutKey = keyof NuxtLayouts
  interface PageMeta {
    layout?: false | LayoutKey | Ref<LayoutKey> | ComputedRef<LayoutKey>
  }
}

export {}
