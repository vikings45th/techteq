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
      mapTypeId: 'terrain',
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
    }

    // スタート地点のマーカーを追加
    if (coordinates.length > 0 && coordinates[0]) {
      const startPosition = new (window as any).google.maps.LatLng(coordinates[0].lat, coordinates[0].lng);
      
      // プライマリーカラーで丸い「S」マーカーを作成
      const secondaryColorName = appConfig.ui?.colors?.secondary || 'ember';
      const secondaryColor = getComputedStyle(document.documentElement)
        .getPropertyValue(`--color-${secondaryColorName}-600`)
        .trim() || '#FB7C2D';
      
      const startMarkerSvg = `
        <svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
          <circle cx="16" cy="16" r="14" fill="${secondaryColor}" stroke="#FFFFFF" stroke-width="2"/>
          <text x="16" y="22" text-anchor="middle" font-size="16" font-weight="bold" fill="#FFFFFF">S</text>
        </svg>
      `;
      
      const startMarkerIcon = {
        url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(startMarkerSvg),
        scaledSize: new (window as any).google.maps.Size(32, 32),
        anchor: new (window as any).google.maps.Point(16, 16),
      };
      
      const startMarker = new (window as any).google.maps.Marker({
        position: startPosition,
        map: mapInstance,
        title: 'スタート地点',
        icon: startMarkerIcon,
      });
      
      markers.push(startMarker);
      bounds.extend(startPosition);
      hasBounds = true;
    }

    // スポットのマーカーを追加
    if (routeState.value.spots && routeState.value.spots.length > 0) {
      routeState.value.spots.forEach((spot, index) => {
        if (spot.lat !== undefined && spot.lng !== undefined) {
          const position = new (window as any).google.maps.LatLng(spot.lat, spot.lng);
          
          // プライマリーカラーでピンアイコンを作成
          const primaryColorName = appConfig.ui?.colors?.primary || 'verdant';
          const primaryColor = getComputedStyle(document.documentElement)
            .getPropertyValue(`--color-${primaryColorName}-600`)
            .trim() || '#43A047';
          const pinSvg = `
            <svg width="24" height="32" viewBox="0 0 24 32" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 0C5.373 0 0 5.373 0 12C0 18.627 12 32 12 32S24 18.627 24 12C24 5.373 18.627 0 12 0Z" fill="${primaryColor}"/>
              <circle cx="12" cy="12" r="8" fill="#FFFFFF"/>
              <text x="12" y="16" text-anchor="middle" font-size="11" font-weight="bold" fill="${primaryColor}">${index + 1}</text>
            </svg>
          `;
          
          const pinIcon = {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(pinSvg),
            scaledSize: new (window as any).google.maps.Size(24, 32),
            anchor: new (window as any).google.maps.Point(12, 32),
          };
          
          // マーカーを作成（プライマリーカラーのピンアイコン）
          const marker = new (window as any).google.maps.Marker({
            position: position,
            map: mapInstance,
            title: spot.name || 'スポット',
            icon: pinIcon,
          });

          markers.push(marker);
          
          // boundsに追加
          bounds.extend(position);
          hasBounds = true;
        }
      });
    }

    // boundsがある場合は表示範囲を調整
    if (hasBounds && mapInstance) {
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
  <h1 class="mt-2 mb-2 text-lg font-bold">{{ routeState.title }}</h1>
  <p class="leading-relaxed mb-2">
    {{ routeState.summary }}
  </p>
  <!-- マップ -->
  <div class="rounded-xl overflow-hidden border border-gray-100 bg-gray-50">
    <div
      id="route-map"
      class="w-full h-72"
    ></div>
  </div>

  <div class="grid grid-cols-3 gap-2 text-center text-xs mb-2">
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

  <!-- 見どころスポット -->
  <div v-if="routeState.spots.length > 0">
    <p class="text-gray-800">見どころスポット</p>
    <ul>
      <li
        v-for="(spot, index) in routeState.spots"
        :key="index"
        class="flex items-start gap-3 py-2 cursor-default"
      >
        <!-- ピンアイコン風のバッジ -->
        <div class="relative mt-0.5 shrink-0 text-primary-600">
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
  <UButton block label="このルートを歩く" color="secondary" class="mb-2 text-lg font-bold rounded-full" @click="startNavigation"/>
  <UButton block label="ルートを再検索" color="primary" variant="outline" :loading="loadingRegenerate" class="mb-2 rounded-full" @click="handleRegenerate" />
  <UButton block label="検索条件を変更" variant="link" @click="handleResearch"/>

  <!-- 再検索中のモーダル -->
  <UModal v-model:open="loadingRegenerate" :dismissible="false" title="ルートを再検索" description="しばらくお待ちください。">
    <template #content>
      <div class="flex flex-col items-center justify-center space-y-4 py-4">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-secondary-600" />
        <div class="text-center space-y-2">
          <p class="text-gray-600">散歩ルートを再建策しています。</p>
          <p class="text-gray-600">しばらくお待ちください。</p>
        </div>
      </div>
    </template>
  </UModal>

  <!-- 評価モーダル -->
  <UModal v-model:open="showRatingModal" title="フィードバック" description="このルートはいかがでしたか？">
    <template #content>
      <div class="flex flex-col items-center justify-center space-y-4 py-4">
        <p class="text-lg font-semibold">
          {{ feedbackSubmitted ? 'ありがとうございました！' : 'このルートはいかがでしたか？' }}
        </p>
        <div v-if="feedbackSubmitted" class="space-y-4 py-4">
          <div class="flex flex-col items-center justify-center space-y-3">
            <div class="text-5xl">✨</div>
            <p class="text-center text-base text-gray-700">
              ご評価ありがとうございました！
            </p>
            <p class="text-center text-sm text-gray-500">
              フィードバックを送信しました。
            </p>
          </div>
        </div>
        <div class="flex justify-center gap-2">
          <button
            v-for="star in 5"
            :key="star"
            @click="rating = star"
            class="text-3xl transition-transform hover:scale-110"
            :class="star <= rating ? 'text-secondary-500' : 'text-gray-300'"
          >
            ★
          </button>
        </div>
        <div v-if="!feedbackSubmitted">
          <UButton
            block
            label="フィードバックを送信"
            variant="outline"
            :loading="submittingFeedback"
            :disabled="rating === 0"
            @click="handleRatingSubmit"
            class="text-lg font-bold rounded-full"
          />
        </div>
      </div>
    </template>
  </UModal>
</template>