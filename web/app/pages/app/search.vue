<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';
  import { useRouteApi } from '~/composables/useRouteApi';

  definePageMeta({
    layout: 'app',
  })

  // UUID生成関数（SSR安全）
  const generateUUID = (): string => {
    if (process.client && typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    // SSR時やcrypto.randomUUIDが使えない場合のフォールバック
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  };

  // 初期値を作成
  const getDefaultPayload = (): ApiRequest => ({
    request_id: generateUUID(),
    theme: 'exercise',
    distance_km: 5,
    start_location: {lat: 35.685175,lng: 139.752799},
    end_location: {lat: 35.685175,lng: 139.752799},
    round_trip: true,
    debug: false
  });

  // 初期値を確実に取得
  const initialPayload = getDefaultPayload();
  
  // useStateから検索条件を取得、なければ初期値を使用して保存
  const savedPayload = useState<ApiRequest>('searchPayload', () => ({ ...initialPayload }));
  
  // savedPayload.valueが確実に存在するようにする
  if (!savedPayload.value) {
    savedPayload.value = { ...initialPayload };
  }
  
  // reactiveでjsonPayloadを作成
  const jsonPayload = reactive<ApiRequest>({ ...savedPayload.value });

  // jsonPayloadの変更をuseStateに保存
  watch(jsonPayload, (newPayload) => {
    savedPayload.value = { ...newPayload };
  }, { deep: true });
  
  const { fetchRoute } = useRouteApi();
  const loadingApi = ref(false);
  const routeState = useState('currentRoute');

  const callApi = async () => {
    loadingApi.value = true;
    try {
      const route = await fetchRoute(jsonPayload);
      routeState.value = route;
      savedPayload.value = { ...jsonPayload };
      await navigateTo(`/app/route?request_id=${jsonPayload.request_id}&route_id=${route.route_id}`);
    } catch (e) {
      console.error(e);
    } finally {
      loadingApi.value = false;
    }
  };

</script>
<template>
  <h1 class="mb-4">目的と距離に合わせてルートを提案します</h1>
  <RouteForm :detailed="true" :jsonpayload="jsonPayload" :loading="loadingApi" @submit-request="callApi"/>
</template>