<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';
  import { useRouteApi } from '~/composables/useRouteApi';

  definePageMeta({
    layout: 'app',
  })

  // request_id(UUID)生成関数
  const generateUUID = (): string => {
    return typeof crypto !== 'undefined' && crypto.randomUUID 
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).substring(2)}`;
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
  
  // useStateから検索条件を取得、なければ初期値を使用して保存
  const jsonPayload = useState<ApiRequest>('searchPayload', () => getDefaultPayload());
  
  const { fetchRoute } = useRouteApi();
  const loadingApi = ref(false);
  const routeState = useState('currentRoute');

  const callApi = async () => {
    if (!jsonPayload.value) {
      console.error('jsonPayload is undefined');
      return;
    }
    loadingApi.value = true;

    try {
      const route = await fetchRoute(jsonPayload.value);
      routeState.value = route;
      await navigateTo(`/app/route?request_id=${jsonPayload.value.request_id}&route_id=${route.route_id}`);
    } catch (e) {
      console.error(e);
    } finally {
      loadingApi.value = false;
    }
  };

</script>
<template>
  <h1 class="mb-4">目的と距離に合わせてルートを提案します</h1>
  <RouteForm v-if="jsonPayload" :detailed="true" :jsonpayload="jsonPayload" :loading="loadingApi" @submit-request="callApi"/>
</template>