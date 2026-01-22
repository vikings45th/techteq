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

  const themeItems = ref(['exercise', 'think', 'refresh', 'nature']);
  // 検索条件の初期値を作成
  const searchParams = ref<ApiRequest>({
    request_id: "initialSearchParamsStateRequestId",
    theme: 'exercise',
    distance_km: 5,
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
      zoom: 15,
      mapTypeId: 'roadmap',
      disableDefaultUI: true, // UIコントロールを非表示
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: false,
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
      searchParams.value.theme = themeParam && themeItems.value.includes(themeParam) ? themeParam : searchParams.value.theme

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
  <h1 class="mb-4">目的と距離に合わせてルートを提案します</h1>
  <div class="space-y-6">
    <div class="space-y-2">
      <p class="text-sm font-semibold text-gray-700 tracking-wide">どんな気分？</p>
      <p class="text-xs text-gray-500">いまの気分に一番近いものを選んでください。</p>
    </div>
    <URadioGroup 
      indicator="hidden" 
      v-model="searchParams.theme" 
      :items="themeItems" 
      variant="card" 
      class="mb-2"
      :ui="{
        fieldset: 'grid grid-cols-2 gap-2'
      }"
    />
    <div class="flex items-start justify-between mb-2 gap-4">
      <div class="space-y-1">
        <p class="text-sm font-semibold text-gray-700 tracking-wide">どれくらい歩く？</p>
        <p class="text-xs text-gray-500">距離を変えると、所要時間や歩数も変わります。</p>
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
        class="mb-2"
    >
      現在地を取得
    </UButton>
    <!-- 開始地点の地図 -->
    <div class="space-y-2 mb-2">
      <p class="text-xs text-gray-500">地図をクリックするか、マーカーをドラッグして開始地点を設定してください。</p>
      <div class="rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
        <div
          id="start-location-map"
          class="w-full h-64"
        ></div>
      </div>
    </div>
    <!-- 開始地点の座標表示（参考用） -->
    <div class="text-xs text-gray-500 mb-2">
      <p>緯度: {{ currentLocation.lat.toFixed(6) }}</p>
      <p>経度: {{ currentLocation.lng.toFixed(6) }}</p>
    </div>
    <UButton 
      color="secondary"
      label="ルートを生成"
      class="w-full mt-2"
      @click="callApi"
    />
  </div>

  <!-- 検索中のモーダル -->
  <UModal v-model:open="loadingApi">
    <template #body>
      <div class="flex items-center justify-center">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-primary-600 mr-3" />
        <h3 class="text-xl font-semibold">検索中...</h3>
      </div>
      <div class="text-center py-4">
        <p class="text-gray-600">ルートを生成しています。しばらくお待ちください。</p>
      </div>
    </template>
  </UModal>
</template>