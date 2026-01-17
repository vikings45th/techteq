<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';
  import { useRouteApi } from '~/composables/useRouteApi';

  definePageMeta({
    layout: 'app',
  })

  // useStateから検索条件を取得、なければ初期値を使用
  const savedPayload = useState<ApiRequest>('searchPayload');
  const jsonPayload = reactive<ApiRequest>(
    savedPayload.value || {
      request_id: crypto.randomUUID(),
      theme: 'exercise',
      distance_km: 5,
      start_location: {lat: 35.685175,lng: 139.752799},
      end_location: {lat: 35.685175,lng: 139.752799},
      round_trip: true,
      debug: false
    }
  );

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