<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';
  import { useRouteApi } from '~/composables/useRouteApi';
  import { useGenerateRequestid } from '~/composables/useGenerateRequestid';
  import { useSearchParams, useCurrentRoute } from '~/composables/states';

  definePageMeta({
    layout: 'app',
  })

  const { generateRequestid } = useGenerateRequestid();
  const { fetchRoute } = useRouteApi();

  const route = useRoute();
  const themeParam = route.query.theme as string | undefined;
  const quicksearch = route.query.quicksearch === 'true';

  const themeItems = ref([{
    label: '体を動かしたい',
    value: 'exercise'
  }, {
    label: '考え事をしたい',
    value: 'think'
  }, {
    label: 'リフレッシュしたい',
    value: 'refresh'
  }, {
    label: '自然を感じたい',
    value: 'nature'
  }]);
  const motivationItems = ref([{
    label: '軽く歩く',
    value: 'light'
  }, {
    label: 'ほどよく歩く',
    value: 'medium'
  }, {
    label: 'しっかり歩く',
    value: 'heavy'
  }]);
  const motivation = ref("light")
  // 検索条件の初期値を作成
  const searchParams = ref<ApiRequest>({
    request_id: "initialSearchParamsStateRequestId",
    theme: 'exercise',
    distance_km: 2,
    start_location: {lat: 35.685175,lng: 139.752799},
    end_location: {lat: 35.685175,lng: 139.752799},
    round_trip: true,
    debug: false
  });

  const locationError = ref<string | null>(null);
  const loadingLocation = ref<boolean>(false);
  const loadingApi = ref<boolean>(false);
  
  const searchParamsState = useSearchParams();
  const routeState = useCurrentRoute();

  const fetchCurrentLocation = (): Promise<void> => {
    if (!navigator.geolocation) {
      locationError.value = 'このブラウザは位置情報取得に対応していません。';
      return Promise.resolve();
    }

    loadingLocation.value = true;
    locationError.value = null;

    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          currentLocation.value = {lat: pos.coords.latitude, lng: pos.coords.longitude};
          
          // 地図が初期化されている場合は、マーカーと地図の中心を更新
          if (mapInstance && startMarker) {
            const position = new (window as any).google.maps.LatLng(pos.coords.latitude, pos.coords.longitude);
            startMarker.setPosition(position);
            mapInstance.setCenter(position);
            mapInstance.setZoom(15);
          }

          loadingLocation.value = false;
          resolve();
        },
        (err) => {
          loadingLocation.value = false;
          locationError.value = '位置情報の取得に失敗しました: ' + err.message;
          resolve(); // エラー時も完了扱いにする
        },
        {
          enableHighAccuracy: true,
          timeout: 100000,
        }
      );
    });
  };

  const callApi = async () => {
    loadingApi.value = true;

    searchParams.value.request_id = generateRequestid();

    // 現在地をsearchParams.start_locationに代入
    searchParams.value.start_location = { ...currentLocation.value };

    //現状startとendの位置は一致させてる。
    //round_tripの計算: 緯度 0.001° ≒ 111m、経度 0.001° ≒ 91m
    //const flag:boolean = Math.abs(startLat.value - endLat.value) < 0.001 && Math.abs(startLng.value - endLng.value) < 0.001;
    //searchParams.value.round_trip = flag;
    searchParams.value.end_location = searchParams.value.start_location;

    // motivation.valueによる分岐
    if (motivation.value === 'light') {
      searchParams.value.distance_km = 1;
    } else if (motivation.value === 'medium') {
      searchParams.value.distance_km = 2;
    } else if (motivation.value === 'heavy') {
      searchParams.value.distance_km = 3;
    }

    try {
      //検索条件を保存し、ルート検索
      searchParamsState.value = searchParams.value;
      const route = await fetchRoute(searchParams.value);

      //検索結果ルートを保存し、ルート画面に遷移
      routeState.value = route;
      await navigateTo(`/app/route?request_id=${searchParams.value.request_id}&route_id=${route.route_id}`);

    } catch (e) {
      console.error(e);
    } finally {
      loadingApi.value = false;
    }
  };

  onMounted(async() => {
    // quicksearch=trueの場合は自動的に検索を実行
    if (quicksearch) {
      loadingApi.value = true;
      searchParams.value.theme = themeParam && themeItems.value.some(item => item.value === themeParam) ? themeParam : searchParams.value.theme

      await fetchCurrentLocation();
      await callApi();
    }else{
      // 保存されている検索条件があれば、searchParamsに代入
      // request_idが初期値でない場合は、以前の検索条件が保存されていると判断
      const hasSavedSearchParams = searchParamsState.value && 
        searchParamsState.value.request_id !== "initialSearchParamsStateRequestId";
      
      if(hasSavedSearchParams){
        searchParams.value = searchParamsState.value
        // 保存されている検索条件の開始地点を現在地に設定
        currentLocation.value = { ...searchParams.value.start_location };
      }else{
        // 初回アクセスまたは初期値の場合は現在地を取得
        await fetchCurrentLocation();
      }
    }
  })

</script>
<template>
  <div class="flex flex-col h-[calc(100vh-var(--ui-header-height))]">
    <!-- 開始地点の地図 -->
    <div class="flex-1 flex flex-col">
      <div class="relative flex-1 bg-gray-50">
        <div
          id="start-location-map"
          class="w-full h-full"
        ></div>
        <!-- 現在地を取得ボタン（地図右下に重ねて表示） -->
        <div class="absolute bottom-4 right-4 z-10">
          <UButton
              size="xl"
              color="primary"
              icon="ic:baseline-my-location"
              :loading="loadingLocation"
              @click="fetchCurrentLocation"
              variant="outline"
              :ui="{
                base: 'shadow-lg bg-white'
              }"
          />
        </div>
      </div>
      <p class="text-xs text-gray-500 px-2 py-1">地図をクリックするか、マーカーをドラッグして開始地点を設定してください。</p>
    </div>
    <!-- フォーム部分（画面下部に固定） -->
    <div class="flex-none shrink-0 px-2 pb-2">
      <div class="overflow-x-auto pt-4 pb-4 mr-2 px-2 scrollbar-hide">
        <URadioGroup 
          indicator="hidden"
          orientation="horizontal"
          v-model="searchParams.theme" 
          :items="themeItems" 
          variant="card"
          :ui="{
            wrapper: 'shrink-0 min-w-[120px]',  
          }"
        />
      </div>
      <div class="text-right text-xs">
        <p class="font-semibold text-primary-600">
          {{ searchParams.distance_km }}km
        </p>
        <p class="text-gray-500">
          約 {{ Math.round(searchParams.distance_km/0.06) }} 分
        </p>
        <p class="text-gray-400">
          約 {{ searchParams.distance_km*1000 }} 歩
        </p>
      </div>
    </div>
    <USlider 
      v-model="searchParams.distance_km" 
      :min="0.5" 
      :max="10" 
      :step="0.5" 
      :default-value="5" 
      class="mb-2"
    />
    <div class="space-y-2 mb-2">
      <p class="text-sm font-semibold text-gray-700 tracking-wide">どこからどこまで？</p>
      <p class="text-xs text-gray-500">現在地をもとに開始地点と終了地点を指定します。</p>
    </div>
    <UButton
        size="xs"
        color="primary"
        :loading="loadingLocation"
        @click="fetchCurrentLocation"
    >
      現在地を取得
    </UButton>
    <!-- 開始地点・終了地点 -->
    <UInput
      v-model.number="searchParams.start_location.lat"
      type="number"
      step="0.000001"
      placeholder="開始地点の緯度"
    />
    <UInput
      v-model.number="searchParams.start_location.lng"
      type="number"
      step="0.000001"
      placeholder="開始地点の経度"
    />
    <UButton 
      color="secondary"
      label="ルートを生成"
      class="w-full mt-2"
      @click="callApi"
    />
  </div>

  <!-- 検索中のモーダル -->
  <UModal v-model:open="loadingApi" :dismissible="false" title="条件に合う散歩ルートを探しています。" description="しばらくお待ちください。">
    <template #content>
      <div class="flex flex-col items-center justify-center space-y-4 py-4">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-secondary-600" />
        <div class="text-center space-y-2">
          <p class="text-gray-600">条件に合う散歩ルートを探しています。</p>
          <p class="text-gray-600">しばらくお待ちください。</p>
        </div>
      </div>
    </template>
  </UModal>
</template>

<style scoped>
.scrollbar-hide {
  -ms-overflow-style: none;  /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}

.scrollbar-hide::-webkit-scrollbar {
  display: none;  /* Chrome, Safari and Opera */
}
</style>