<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';
  import { useRouteApi } from '~/composables/useRouteApi';

  definePageMeta({
    layout: 'app',
  })

  import type { Route } from '~/types/route';

  const { fetchRoute } = useRouteApi();
  const routeData = useState<Route>('currentRoute');
  const savedPayload = useState<ApiRequest>('searchPayload');

  let mapInstance: any = null;
  let flightPath: any = null;

  function destroyMap() {
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
    const coordinates = routeData.value.polyline;

    // まずはデフォルトの中心・ズームでマップを作る
    let center = { lat: 0, lng: -180 };
    let zoom = 2;

    mapInstance = new (window as any).google.maps.Map(mapElement, {
      zoom,
      center,
      mapTypeId: 'terrain',
      // すべてのインタラクションを無効化
      disableDefaultUI: true,
      draggable: false,
      scrollwheel: false,
      disableDoubleClickZoom: true,
      keyboardShortcuts: false,
      clickableIcons: false,
      gestureHandling: 'none',
    });

    // ここから polyline がある場合だけ bounds を使って再調整
    if (coordinates.length > 0 && mapInstance) {
      const bounds = new (window as any).google.maps.LatLngBounds();

      coordinates.forEach((p) => {
        bounds.extend(new (window as any).google.maps.LatLng(p.lat, p.lng));
      });

      mapInstance.fitBounds(bounds);
    }

    if (coordinates.length > 0) {
      // 既存のflightPathがあれば削除
      if (flightPath) {
        flightPath.setMap(null);
      }
      
      flightPath = new (window as any).google.maps.Polyline({
        path: coordinates,
        geodesic: true,
        strokeColor: "#FF0000",
        strokeOpacity: 1.0,
        strokeWeight: 2,
      });
      flightPath.setMap(mapInstance);
    }
  }

  const startNavigation = () => {
    if (!routeData.value?.nav_waypoints || routeData.value.nav_waypoints.length < 2) return;
    
    const points = routeData.value.nav_waypoints;
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
  };

  const loadingRegenerate = ref(false);

  const handleResearch = async () => {
    await navigateTo('/app/search');
  };

  const handleRegenerate = async () => {
    if (!savedPayload.value) {
      await navigateTo('/app/search');
      return;
    }

    loadingRegenerate.value = true;
    try {
      const payload = { ...savedPayload.value, request_id: crypto.randomUUID() };
      routeData.value = await fetchRoute(payload);
      savedPayload.value = payload;
      await nextTick();
      initMap();
    } catch (e) {
      console.error(e);
    } finally {
      loadingRegenerate.value = false;
    }
  };

  onMounted(async () => {
    if (!routeData.value) {
      // routeデータが存在しない場合は、searchページにリダイレクト
      await navigateTo('/app/search');
    }

    initMap();
  });

  // コンポーネントがアンマウントされる時にもマップを破棄
  onBeforeUnmount(() => {
    destroyMap();
  });
</script>

<template>
  <h1 class="mb-4">生成されたルートがこちらです</h1>
  <div v-if="routeData">
    <div>
      <h2>{{ routeData.title }}</h2>
      <div v-if="savedPayload" class="mt-2 flex flex-wrap gap-2 text-xs text-gray-600">
        <span class="px-2 py-1 bg-gray-100 rounded">
          テーマ: {{ savedPayload.theme }}
        </span>
        <span class="px-2 py-1 bg-gray-100 rounded">
          距離: {{ savedPayload.distance_km }}km
        </span>
        <span class="px-2 py-1 bg-gray-100 rounded">
          開始地点: {{ savedPayload.start_location.lat.toFixed(6) }}, {{ savedPayload.start_location.lng.toFixed(6) }}
        </span>
      </div>
    </div>
    <div>
      <!-- マップ（静的イメージ風） -->
      <div class="rounded-xl overflow-hidden border border-gray-100 bg-gray-50">
        <div
          id="route-map"
          class="w-full h-72 pointer-events-none select-none"
          style="cursor: default;"
        ></div>
      </div>

      <!-- サマリー & 数字情報 -->
      <div class="rounded-xl bg-gray-50 px-4 py-3 border border-gray-100 space-y-3">
        <div class="space-y-1">
          <p class="text-sm font-semibold text-gray-800">このルートについて</p>
          <p class="text-sm text-gray-600 leading-relaxed">
            {{ routeData.summary }}
          </p>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center text-xs">
          <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
            <p class="text-[11px] text-gray-500">距離</p>
            <p class="mt-1 text-sm font-semibold text-primary-600">
              {{ routeData.distance_km }}km
            </p>
          </div>
          <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
            <p class="text-[11px] text-gray-500">歩数目安</p>
            <p class="mt-1 text-sm font-semibold text-emerald-600">
              {{ routeData.distance_km! * 1000 }}歩
            </p>
          </div>
          <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
            <p class="text-[11px] text-gray-500">所要時間</p>
            <p class="mt-1 text-sm font-semibold text-indigo-600">
              {{ routeData.duration_min }}分
            </p>
          </div>
        </div>
      </div>

      <!-- 見どころスポット -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <p class="text-sm font-semibold text-gray-800">見どころスポット</p>
          <p class="text-[11px] text-gray-500">
            全 {{ routeData.spots.length }} か所
          </p>
        </div>
        <ul class="space-y-1.5">
          <li
            v-for="(spot, index) in routeData.spots"
            :key="index"
            class="flex items-start gap-3 py-2 cursor-default"
          >
            <div class="mt-0.5 h-5 w-5 flex items-center justify-center text-[11px] font-medium text-gray-400">
              {{ index + 1 }}.
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-gray-700 truncate">
                {{ spot.name || 'スポット名未設定' }}
              </p>
              <p class="text-[11px] text-gray-400 mt-0.5">
                {{ spot.type || 'スポット' }}
              </p>
            </div>
          </li>
        </ul>
      </div>
    </div>
    <div>
      <UButton label="検索条件を変更" color="neutral" variant="outline" @click="handleResearch" />
      <UButton label="もう一度提案求む" color="neutral" variant="outline" :loading="loadingRegenerate" @click="handleRegenerate" />
      <UButton label="これでいく！" color="secondary" @click="startNavigation"/>
    </div>
  </div>
</template>