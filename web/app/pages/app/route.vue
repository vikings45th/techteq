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

  // 有効数字2桁に丸める関数
  const toSignificantDigits = (num: number, digits: number = 2): number => {
    if (num === 0) return 0;
    const magnitude = Math.floor(Math.log10(Math.abs(num)));
    const factor = Math.pow(10, digits - magnitude - 1);
    return Math.round(num * factor) / factor;
  };

  // マーカーとinterval IDを管理する変数
  const mapInstance = ref<any>(null);
  const flightPath = ref<any>(null);
  const markers = ref<any[]>([]);
  const checkGoogleMapsInterval = ref<NodeJS.Timeout | null>(null);

  // 地図の中心位置
  const mapCenter = ref<{lat: number, lng: number}>({
    lat: 35.685175,
    lng: 139.752799
  });

  function destroyMap() {
    // マーカーを削除
    markers.value.forEach((marker) => {
      marker.map = null;
    });
    markers.value = [];
    
    if (flightPath.value) {
      flightPath.value.setMap(null);
      flightPath.value = null;
    }
    
    if (mapInstance.value) {
      // マップ上のすべてのオーバーレイを削除
      if (mapInstance.value.overlayMapTypes) {
        mapInstance.value.overlayMapTypes.clear();
      }
      // マップインスタンスをnullに設定
      mapInstance.value = null;
    }

    const mapElement = document.querySelector('gmp-map') as any;
    // DOM要素の内容をクリア
    if (mapElement) {
      mapElement.innerHTML = '';
    }
  }

  const initMap = async () => {
    const mapElement = document.querySelector('gmp-map') as any;
    if (!mapElement || !(window as any).google) {
      return;
    }

    // Dynamic Library Importを使用して必要なライブラリを読み込む
    const { Map, InfoWindow } = await (window as any).google.maps.importLibrary('maps');
    const { AdvancedMarkerElement, PinElement } = await (window as any).google.maps.importLibrary('marker');

    // 既にマップが初期化されている場合は削除
    if (mapInstance.value) {
      destroyMap();
    }
    
    // DOM要素をクリア（既存のマップ要素を削除）
    mapElement.innerHTML = '';

    // ルートの座標を取得（デフォルト値は空配列）
    const coordinates = routeState.value.polyline;

    // gmp-map の innerMap を使用してマップオプションを設定
    mapElement.innerMap.setOptions({
      disableDefaultUI: true,
      draggable: true,
      scrollwheel: true,
      disableDoubleClickZoom: true,
      keyboardShortcuts: false,
      clickableIcons: false,
    });

    // mapInstance を innerMap に設定
    mapInstance.value = mapElement.innerMap;

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

    const infoWindow = new InfoWindow();

    // スタート地点のマーカーを追加
    if (coordinates.length > 0 && coordinates[0]) {
      const startPosition = { lat: coordinates[0].lat, lng: coordinates[0].lng };
      
      // 歩いている人のSVGアイコンをData URLとして作成
      const walkingSvgString = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24"><path fill="white" d="M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2s-2 .9-2 2s.9 2 2 2M9.8 8.9L7 23h2.1l1.8-8l2.1 2v6h2v-7.5l-2.1-2l.6-3C14.8 12 16.8 13 19 13v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1c-.3 0-.5.1-.8.1L6 8.3V13h2V9.6z"/></svg>';
      const walkingSvgDataUrl = 'data:image/svg+xml,' + encodeURIComponent(walkingSvgString);

      const startPin = new PinElement({
        scale: 1.5,
        background: '#FB7C2D',
        borderColor: '#FFFFFF',
        glyphSrc: walkingSvgDataUrl
      });
      
      // 高度なマーカーを使用
      const startMarker = new AdvancedMarkerElement({
        position: startPosition,
        title: 'スタート地点',
      });
      // Append the pin to the marker.
      startMarker.append(startPin);
      // Append the marker to the map.
      mapElement.append(startMarker);
      
      markers.value.push(startMarker);
      bounds.extend(new (window as any).google.maps.LatLng(startPosition.lat, startPosition.lng));
      hasBounds = true;
    }

    // スポットのマーカーを追加
    if (routeState.value.spots && routeState.value.spots.length > 0) {
      routeState.value.spots.forEach((spot, index) => {
        if (spot.lat !== undefined && spot.lng !== undefined) {
          const position = { lat: spot.lat, lng: spot.lng };
          
          // ピンアイコンSVGをHTML要素として作成
          const pinElement = new PinElement({
            background: '#43A047',
            borderColor: '#FFFFFF',
            glyphText: `${index+1}`,
            glyphColor: 'white',
          });
          
          // 高度なマーカーを使用
          const marker = new AdvancedMarkerElement({
            position: position,
            title: spot.name || 'スポット',
            gmpClickable: true,
          });
          // Append the pin to the marker.
          marker.append(pinElement);
          // Append the marker to the map.
          mapElement.append(marker);
          markers.value.push(marker);

          // Add a click listener for each marker, and set up the info window.
        marker.addListener('click', () => {
            infoWindow.close();
            infoWindow.setContent(marker.title);
            infoWindow.open(marker.map, marker);
        });
          
          // boundsに追加
          bounds.extend(new (window as any).google.maps.LatLng(position.lat, position.lng));
          hasBounds = true;
        }
      });
    }

    // boundsがある場合は表示範囲を調整
    if (hasBounds && mapInstance.value) {
      // UCardの高さを取得（bottom-4の位置にあるUCard）
      const cardElement = document.querySelector('.absolute.bottom-4') as HTMLElement;
      const cardHeight = cardElement ? cardElement.offsetHeight + 32 : 0; // bottom-4 = 16px * 2 = 32px
      const mapHeight = mapElement.clientHeight;
      
      // UCardを除いた高さの中心にboundsの中心が来るようにパディングを設定
      // 利用可能な高さの中心 = (mapHeight - cardHeight) / 2
      // マップ全体の中心 = mapHeight / 2
      // 下パディングを調整して、boundsの中心を利用可能な高さの中心に配置
      const availableHeight = mapHeight - cardHeight;
      const targetCenterY = availableHeight / 2;
      
      // 下パディングを計算（boundsの中心がtargetCenterYに来るように）
      const bottomPadding = mapHeight - targetCenterY * 2;
      
      // fitBoundsで直接中心に表示
      mapInstance.value.fitBounds(bounds, {
        top: 0,
        right: 0,
        bottom: bottomPadding,
        left: 0
      });
    }

    // polylineを描画
    if (coordinates.length > 0) {
      // 既存のflightPathがあれば削除
      if (flightPath.value) {
        flightPath.value.setMap(null);
      }
      
      // セカンダリーカラーをCSS変数から取得
      const secondaryColorName = appConfig.ui?.colors?.secondary || 'ember';
      const secondaryColor = getComputedStyle(document.documentElement)
        .getPropertyValue(`--color-${secondaryColorName}-600`)
        .trim() || '#FB7C2D';
      
      flightPath.value = new (window as any).google.maps.Polyline({
        path: coordinates,
        geodesic: true,
        strokeColor: secondaryColor,
        strokeOpacity: 1.0,
        strokeWeight: 4,
      });
      flightPath.value.setMap(mapInstance.value);
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

    // ルートの座標から地図の中心を計算
    const coordinates = routeState.value.polyline;
    if (coordinates.length > 0) {
      const centerLat = coordinates.reduce((sum, p) => sum + p.lat, 0) / coordinates.length;
      const centerLng = coordinates.reduce((sum, p) => sum + p.lng, 0) / coordinates.length;
      mapCenter.value = { lat: centerLat, lng: centerLng };
    }

    // DOMが完全にレンダリングされた後に地図を初期化
    await nextTick();
    
    // 地図を初期化（Google Maps APIの読み込みを待つ）
    checkGoogleMapsInterval.value = setInterval(() => {
      if ((window as any).google) {
        if (checkGoogleMapsInterval.value) {
          clearInterval(checkGoogleMapsInterval.value);
          checkGoogleMapsInterval.value = null;
        }
        // さらに少し待ってから初期化（レイアウトが確定するまで）
        setTimeout(() => {
          initMap();
        }, 200);
      }
    }, 100);

    // タイムアウト（10秒後）
    setTimeout(() => {
      if (checkGoogleMapsInterval.value) {
        clearInterval(checkGoogleMapsInterval.value);
        checkGoogleMapsInterval.value = null;
      }
    }, 10000);
  });

  // コンポーネントがアンマウントされる時にもマップを破棄
  onBeforeUnmount(() => {
    // interval をクリア
    if (checkGoogleMapsInterval.value) {
      clearInterval(checkGoogleMapsInterval.value);
      checkGoogleMapsInterval.value = null;
    }

    destroyMap();
  });
</script>

<template>
  <div class="flex flex-col h-dvh">
    <!-- マップ -->
    <div class="flex-1 relative border border-gray-100 bg-gray-50">
      <gmp-map
        :center="{ lat: mapCenter.lat, lng: mapCenter.lng }"
        :zoom="15"
        map-id="9153bea12861ba5a84e2b6d3"
        class="w-full h-full"></gmp-map>
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
              {{ toSignificantDigits(routeState.distance_km) }}km
            </p>
            <p class="mt-1 text-lg font-bold text-indigo-600">
              {{ toSignificantDigits(routeState.duration_min) }}分
            </p>
            <p class="mt-1 text-lg font-bold text-emerald-600">
              {{ toSignificantDigits(Math.round(routeState.distance_km! * 100000 / 76)) }}歩
            </p>
          </div>
        </template>

        <template #footer>
          <UButton block label="このルートを歩く" color="secondary" class="text-lg font-bold rounded-full" @click="startNavigation"/>
        </template>
      </UCard>

      <!-- 見どころスポット -->
      <div class="flex gap-2 mt-2">
        <UButton block label="ルートを再検索" color="secondary" variant="outline" :loading="loadingRegenerate" @click="handleRegenerate" class="flex-1 bg-white" />
        <UButton block label="検索条件を変更" color="secondary" variant="outline" @click="handleResearch" class="flex-1 bg-white" />
      </div>
    </div>
  </div>

  <!-- 再検索中のモーダル -->
  <UModal v-model:open="loadingRegenerate" :dismissible="false" title="ルートを再検索" description="しばらくお待ちください。">
    <template #content>
      <div class="flex flex-col items-center justify-center space-y-4 py-4">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-secondary-600" />
        <div class="text-center space-y-2">
          <p class="text-gray-600">散歩ルートを再検索しています。</p>
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
            :class="star <= rating ? 'text-yellow-400' : 'text-gray-300'"
          >
            ★
          </button>
        </div>
        <div v-if="!feedbackSubmitted">
          <UButton
            block
            label="フィードバックを送信"
            variant="outline"
            color="secondary"
            :loading="submittingFeedback"
            :disabled="rating === 0"
            @click="handleRatingSubmit"
            class="text-lg font-bold rounded-full mx-2"
          />
        </div>
      </div>
    </template>
  </UModal>
</template>