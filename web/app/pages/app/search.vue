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
  const appConfig = useAppConfig();

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
      disableDefaultUI: true,
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: true,
      keyboardShortcuts: false,
      clickableIcons: false,
    });

    // 地図のサイズを再計算（flexboxで高さが確定した後に必要）
    setTimeout(() => {
      if (mapInstance) {
        (window as any).google.maps.event.trigger(mapInstance, 'resize');
      }
    }, 300);

    // ResizeObserverで要素のサイズ変更を監視
    if (mapElement && mapInstance) {
      const resizeObserver = new ResizeObserver(() => {
        if (mapInstance) {
          (window as any).google.maps.event.trigger(mapInstance, 'resize');
        }
      });
      resizeObserver.observe(mapElement);
      
      // クリーンアップ用に保存
      (mapElement as any).__resizeObserver = resizeObserver;
    }

    // 開始地点のマーカーを作成（ドラッグ可能）
    const position = new (window as any).google.maps.LatLng(center.lat, center.lng);
    
    // セカンダリーカラーで現在地アイコンを作成
    const secondaryColorName = appConfig.ui?.colors?.secondary || 'ember';
      const secondaryColor = getComputedStyle(document.documentElement)
        .getPropertyValue(`--color-${secondaryColorName}-600`)
        .trim() || '#FB7C2D';
    
    // ピンアイコンSVG
    const pinIconSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24">
        <path fill="${secondaryColor}" d="M12 11c-1.33 0-4 .67-4 2v.16c.97 1.12 2.4 1.84 4 1.84s3.03-.72 4-1.84V13c0-1.33-2.67-2-4-2m0-1c1.1 0 2-.9 2-2s-.9-2-2-2s-2 .9-2 2s.9 2 2 2m0-8c4.2 0 8 3.22 8 8.2c0 3.32-2.67 7.25-8 11.8c-5.33-4.55-8-8.48-8-11.8C4 5.22 7.8 2 12 2"/>
      </svg>
    `;
    
    const pinIcon = {
      url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(pinIconSvg),
      scaledSize: new (window as any).google.maps.Size(40, 40),
      anchor: new (window as any).google.maps.Point(20, 20),
    };
    
    startMarker = new (window as any).google.maps.Marker({
      position: position,
      map: mapInstance,
      title: '開始地点',
      draggable: true, // マーカーをドラッグ可能にする
      icon: pinIcon,
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

    // DOMが完全にレンダリングされた後に地図を初期化
    await nextTick();
    
    // 地図を初期化（Google Maps APIの読み込みを待つ）
    const checkGoogleMaps = setInterval(() => {
      if ((window as any).google) {
        clearInterval(checkGoogleMaps);
        // さらに少し待ってから初期化（レイアウトが確定するまで）
        setTimeout(() => {
          initMap();
        }, 200);
      }
    }, 100);

    // タイムアウト（10秒後）
    setTimeout(() => {
      clearInterval(checkGoogleMaps);
    }, 10000);
  });

  // コンポーネントがアンマウントされる時にマップを破棄
  onBeforeUnmount(() => {
    const mapElement = document.getElementById("start-location-map");
    if (mapElement && (mapElement as any).__resizeObserver) {
      (mapElement as any).__resizeObserver.disconnect();
    }
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
      <div class="overflow-x-auto pb-4 mr-2 px-2 scrollbar-hide">
        <URadioGroup 
          indicator="hidden"
          orientation="horizontal"
          v-model="motivation" 
          :items="motivationItems" 
          variant="card"
          :ui="{
            wrapper: 'shrink-0 min-w-[120px]', 
          }"
        />
      </div>
      <UButton
        block
        color="secondary"
        label="散歩ルートを探す"
        class="my-4 text-lg font-bold rounded-full"
        @click="callApi"
      />
    </div>
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