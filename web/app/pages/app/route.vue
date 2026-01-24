<script setup lang="ts">
  import { useRouteApi } from '~/composables/useRouteApi';
  import { useGenerateRequestid } from '~/composables/useGenerateRequestid';
  import { useSearchParams, useCurrentRoute } from '~/composables/states';

  definePageMeta({
    layout: 'app',
  })
  const { fetchRoute, submitRouteFeedback } = useRouteApi();
  const { generateRequestid } = useGenerateRequestid();

  const searchParamsState = useSearchParams();
  const routeState = useCurrentRoute();
  const appConfig = useAppConfig();

  const loadingRegenerate = ref(false);
  const showRatingModal = ref(false);
  const rating = ref(0);
  const submittingFeedback = ref(false);
  const feedbackSubmitted = ref(false);

  let mapInstance: any = null;
  let flightPath: any = null;
  let markers: any[] = [];

  function destroyMap() {
    // マーカーを削除
    markers.forEach((marker) => {
      marker.setMap(null);
    });
    markers = [];
    
    if (flightPath) {
      flightPath.setMap(null);
      flightPath = null;
    }
    
    if (mapInstance) {
      // マップ上のすべてのオーバーレイを削除
      if (mapInstance.overlayMapTypes) {
        mapInstance.overlayMapTypes.clear();
      }
      // マップインスタンスをnullに設定
      mapInstance = null;
    }
    
    // DOM要素の内容をクリア
    const mapElement = document.getElementById("route-map");
    if (mapElement) {
      mapElement.innerHTML = '';
    }
  }

  const initMap = () => {
    const mapElement = document.getElementById("route-map");
    if (!mapElement || !(window as any).google) {
      return;
    }

    // 既にマップが初期化されている場合は削除
    if (mapInstance) {
      destroyMap();
    }
    
    // DOM要素をクリア（既存のマップ要素を削除）
    mapElement.innerHTML = '';

    // ルートの座標を取得（デフォルト値は空配列）
    const coordinates = routeState.value.polyline;

    // まずはデフォルトの中心・ズームでマップを作る
    let center = { lat: 0, lng: -180 };
    let zoom = 17;

    mapInstance = new (window as any).google.maps.Map(mapElement, {
      zoom,
      center,
      disableDefaultUI: true,
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: true,
      keyboardShortcuts: false,
      clickableIcons: false,
    });

    // bounds を使って表示範囲を調整
    const bounds = new (window as any).google.maps.LatLngBounds();
    let hasBounds = false;

    // polylineの座標をboundsに追加
    if (coordinates.length > 0) {
      coordinates.forEach((p) => {
        bounds.extend(new (window as any).google.maps.LatLng(p.lat, p.lng));
        hasBounds = true;
      });

      mapInstance.fitBounds(bounds);
    }

    // polylineを描画
    if (coordinates.length > 0) {
      // 既存のflightPathがあれば削除
      if (flightPath) {
        flightPath.setMap(null);
      }
      
      // セカンダリーカラーをCSS変数から取得
      const secondaryColorName = appConfig.ui?.colors?.secondary || 'ember';
      const secondaryColor = getComputedStyle(document.documentElement)
        .getPropertyValue(`--color-${secondaryColorName}-600`)
        .trim() || '#FB7C2D';
      
      flightPath = new (window as any).google.maps.Polyline({
        path: coordinates,
        geodesic: true,
        strokeColor: secondaryColor,
        strokeOpacity: 1.0,
        strokeWeight: 4,
      });
      flightPath.setMap(mapInstance);
    }
  }

  const startNavigation = () => {
    if (!routeState.value?.nav_waypoints || routeState.value.nav_waypoints.length < 2) return;
    
    const points = routeState.value.nav_waypoints;
    const origin = points[0]!;
    const destination = points[points.length - 1]!;
    const waypoints = points.slice(1, -1).map(p => `${p.lat},${p.lng}`).join('|');

    const params = new URLSearchParams({
      api: '1',
      origin: `${origin.lat},${origin.lng}`,
      destination: `${destination.lat},${destination.lng}`,
      travelmode: 'walking',
    });

    if (waypoints) params.set('waypoints', waypoints);
    window.open(`https://www.google.com/maps/dir/?${params.toString()}`, '_blank');
    
    // 元のタブで評価モーダルを表示
    showRatingModal.value = true;
  };

  const handleRatingSubmit = async () => {
    if (rating.value === 0) {
      return;
    }

    if (!searchParamsState.value || !routeState.value) {
      return;
    }

    // 初期値の場合はreturn
    if (
      searchParamsState.value.request_id === "initialSearchParamsStateRequestId" ||
      routeState.value.route_id === "initialRouteStateRequestId"
    ) {
      return;
    }

    submittingFeedback.value = true;
    try {
      const response = await submitRouteFeedback({
        request_id: searchParamsState.value.request_id,
        route_id: routeState.value.route_id,
        rating: rating.value,
      });

      // 送信成功時（statusが"accepted"の場合）
      if (response && response.status === "accepted") {
        feedbackSubmitted.value = true;
        // 2秒後にモーダルを閉じる
        setTimeout(() => {
          showRatingModal.value = false;
          feedbackSubmitted.value = false;
          rating.value = 0;
        }, 2000);
      }
    } catch (error) {
      console.error('評価の送信に失敗しました:', error);
    } finally {
      submittingFeedback.value = false;
    }
  };

  const handleResearch = async () => {
    await navigateTo('/app/search');
  };

  const handleRegenerate = async () => {
    if (!searchParamsState.value) {
      await navigateTo('/app/search');
      return;
    }

    loadingRegenerate.value = true;
    try {
      //request_idだけ新規のものに修正し、検索条件を保存し、ルート検索
      const payload = { ...searchParamsState.value, request_id: generateRequestid() };
      searchParamsState.value = payload;
      const regenedRoute = await fetchRoute(payload);

      //検索結果ルートを保存
      routeState.value = regenedRoute

      //DOM更新
      await nextTick();
      initMap();

    } catch (e) {
      console.error(e);
    } finally {
      loadingRegenerate.value = false;
    }
  };

  onMounted(async () => {
    // routeデータが存在しない、または初期値の場合は、searchページにリダイレクト
    if (!routeState.value || routeState.value.route_id === "initialRouteStateRequestId") {
      await navigateTo('/app/search');
      return;
    }

    initMap();
  });

  // コンポーネントがアンマウントされる時にもマップを破棄
  onBeforeUnmount(() => {
    destroyMap();
  });
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-var(--ui-header-height))]">
    <!-- マップ -->
    <div class="flex-1 relative border border-gray-100 bg-gray-50">
      <div
        id="route-map"
        class="w-full h-full"
      ></div>
    </div>
    <div class="absolute bottom-4 z-10 px-2">
      <UCard>
        <template #header>
          <h1 class="text-lg font-bold mb-2">{{ routeState.title }}</h1>
          <p class="text-sm mb-2">
            {{ routeState.summary }}
          </p>
          <div class="grid grid-cols-3 gap-2 text-center text-xs">
            <p class="mt-1 text-lg font-bold text-primary-600">
              {{ routeState.distance_km }}km
            </p>
            <p class="mt-1 text-lg font-bold text-indigo-600">
              {{ routeState.duration_min }}分
            </p>
            <p class="mt-1 text-lg font-bold text-emerald-600">
              {{ Math.round(routeState.distance_km! * 100000 / 76) }}歩
            </p>
          </div>
        </template>

        <div v-if="routeState.spots.length > 0">
          <ul>
            <li
              v-for="(spot, index) in routeState.spots"
              :key="index"
              class="flex gap-3 py-2 cursor-default items-center"
            >
              <!-- ピンアイコン風のバッジ -->
              <div class="relative shrink-0 text-primary-600">
                <svg 
                  width="24" 
                  height="32" 
                  viewBox="0 0 24 32" 
                  fill="none" 
                  xmlns="http://www.w3.org/2000/svg"
                  class="drop-shadow-sm"
                >
                  <!-- ピンの影部分 -->
                  <path 
                    d="M12 0C5.373 0 0 5.373 0 12C0 18.627 12 32 12 32S24 18.627 24 12C24 5.373 18.627 0 12 0Z" 
                    fill="currentColor"
                  />
                  <!-- 番号を表示する円 -->
                  <circle 
                    cx="12" 
                    cy="12" 
                    r="8" 
                    fill="#FFFFFF"
                  />
                  <text 
                    x="12" 
                    y="16" 
                    text-anchor="middle" 
                    font-size="11" 
                    font-weight="bold" 
                    fill="currentColor"
                  >
                    {{ index + 1 }}
                  </text>
                </svg>
              </div>
              <p class="text-sm text-gray-700 truncate">
                {{ spot.name || 'スポット名未設定' }}
              </p>
            </li>
          </ul>
        </div>

        <template #footer>
          <UButton block label="このルートを歩く" color="secondary" class="mb-2 text-lg font-bold rounded-full" @click="startNavigation"/>
        </template>
      </UCard>

      <!-- 見どころスポット -->
      <div class="flex gap-2 mt-2">
        <UButton block label="ルートを再検索" variant="outline" :loading="loadingRegenerate" @click="handleRegenerate" class="flex-1 bg-white" />
        <UButton block label="検索条件を変更" variant="outline" @click="handleResearch" class="flex-1 bg-white" />
      </div>
    </div>
  </div>
</template>