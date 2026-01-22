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
  // 検索条件の初期値を作成
  const searchParams = ref<ApiRequest>({
    request_id: "initialSearchParamsStateRequestId",
    theme: 'exercise',
    distance_km: 3,
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

  // 現在地を保存する変数
  const currentLocation = ref<{lat: number, lng: number}>({
    lat: 35.685175,
    lng: 139.752799
  });

  // 地図関連
  let mapInstance: any = null;
  let startMarker: any = null;

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
    searchParams.value.end_location = searchParams.value.start_location

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

  const initMap = () => {
    const mapElement = document.getElementById("start-location-map");
    if (!mapElement || !(window as any).google) {
      return;
    }

    // 既にマップが初期化されている場合は削除
    if (mapInstance) {
      if (startMarker) {
        startMarker.setMap(null);
        startMarker = null;
      }
      mapInstance = null;
    }

    // 現在地の座標を取得
    const center = {
      lat: currentLocation.value.lat,
      lng: currentLocation.value.lng
    };

    // 地図を初期化（ドラッグ可能にする）
    mapInstance = new (window as any).google.maps.Map(mapElement, {
      center,
      zoom: 16,
      mapTypeId: 'terrain',
      disableDefaultUI: true,
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: true,
      keyboardShortcuts: false,
      clickableIcons: false,
    });

    // 開始地点のマーカーを作成（ドラッグ可能）
    const position = new (window as any).google.maps.LatLng(center.lat, center.lng);
    startMarker = new (window as any).google.maps.Marker({
      position: position,
      map: mapInstance,
      title: '開始地点',
      draggable: true, // マーカーをドラッグ可能にする
    });

    // マーカーがドラッグされたときに位置を更新
    startMarker.addListener('dragend', (event: any) => {
      const lat = event.latLng.lat();
      const lng = event.latLng.lng();
      currentLocation.value = { lat, lng };
    });

    // 地図がクリックされたときにもマーカーを移動
    mapInstance.addListener('click', (event: any) => {
      const lat = event.latLng.lat();
      const lng = event.latLng.lng();
      const position = new (window as any).google.maps.LatLng(lat, lng);
      startMarker.setPosition(position);
      currentLocation.value = { lat, lng };
    });
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

    // 地図を初期化（Google Maps APIの読み込みを待つ）
    const checkGoogleMaps = setInterval(() => {
      if ((window as any).google) {
        clearInterval(checkGoogleMaps);
        initMap();
      }
    }, 100);

    // タイムアウト（10秒後）
    setTimeout(() => {
      clearInterval(checkGoogleMaps);
    }, 10000);
  });

  // コンポーネントがアンマウントされる時にマップを破棄
  onBeforeUnmount(() => {
    if (startMarker) {
      startMarker.setMap(null);
      startMarker = null;
    }
    if (mapInstance) {
      mapInstance = null;
    }
  });

</script>
<template>
  <h1 class="text-lg font-bold mt-2 mb-2">散歩ルートを決める</h1>
  <p class="text-gray-700 tracking-wide mb-2">どんな気分？</p>
  <URadioGroup 
    indicator="hidden" 
    v-model="searchParams.theme" 
    :items="themeItems" 
    variant="card" 
    :ui="{
      fieldset: 'grid grid-cols-2 gap-2 mb-2',
    }"
  />
  <div class="flex items-center justify-between mb-2">
    <p class="text-gray-700 tracking-wide">どれくらい歩く？</p>
    <p class="font-semibold text-primary-600">{{searchParams.distance_km}}km</p>
  </div>
  <USlider 
    v-model="searchParams.distance_km" 
    :min="1" 
    :max="9" 
    :step="0.5" 
    :default-value="searchParams.distance_km"
    class="mb-2"
  />
  <div class="mb-2">
    <p class="text-gray-700 tracking-wide mb-2">どこから歩く？</p>
  </div>
  <!-- 開始地点の地図 -->
  <div class="space-y-2 mb-2">
    <div class="relative rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
      <div
        id="start-location-map"
        class="w-full h-64"
      ></div>
      <!-- 現在地を取得ボタン（地図右上に重ねて表示） -->
      <div class="absolute top-2 right-2 z-10">
        <UButton
            size="xs"
            color="primary"
            :loading="loadingLocation"
            @click="fetchCurrentLocation"
            variant="outline"
            :ui="{
              base: 'shadow-lg bg-white'
            }"
        >
          <span v-if="loadingLocation">取得中...</span>
          <span v-else>現在地を<br/>取得</span>
        </UButton>
      </div>
    </div>
    <p class="text-xs text-gray-500">地図をクリックするか、マーカーをドラッグして開始地点を設定してください。</p>
  </div>
  <UButton
    block
    color="secondary"
    label="散歩ルートを探す"
    class="mt-2 text-lg font-bold rounded-full"
    @click="callApi"
  />

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