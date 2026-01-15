<script setup lang="ts">
interface Route {
  theme?: string;
  title?: string;
  polyline?: Array<{ lat: number; lng: number }>;
  summary?: string;
  distance_km?: number;
  duration_min?: number;
  spots: Array<{ name?: string; type?: string }>;
}

const props = defineProps<{
  route: Route | null;
  isOpen?: boolean;
}>();

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

function initMap() {
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
  const coordinates = props.route?.polyline || [];

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

    coordinates.forEach((p: { lat: number; lng: number }) => {
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

// routeが変更された時にマップを初期化
watch(() => props.route, (newRoute) => {
  if (newRoute) {
    nextTick(() => {
      // Google Maps APIが読み込まれるまで待つ
      const checkGoogleMaps = setInterval(() => {
        if (typeof window !== 'undefined' && (window as any).google) {
          clearInterval(checkGoogleMaps);
          initMap();
        }
      }, 100);

      // タイムアウト（5秒後）
      setTimeout(() => {
        clearInterval(checkGoogleMaps);
      }, 5000);
    });
  }
}, { immediate: true });

// モーダルが閉じられた時にマップを破棄
watch(() => props.isOpen, (isOpen) => {
  if (isOpen === false) {
    destroyMap();
  }
});

// コンポーネントがアンマウントされる時にもマップを破棄
onBeforeUnmount(() => {
  destroyMap();
});
</script>

<template>
  <div v-if="route" class="space-y-6">
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
          {{ route.summary }}
        </p>
      </div>
      <div class="grid grid-cols-3 gap-2 text-center text-xs">
        <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
          <p class="text-[11px] text-gray-500">距離</p>
          <p class="mt-1 text-sm font-semibold text-primary-600">
            {{ route.distance_km }}km
          </p>
        </div>
        <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
          <p class="text-[11px] text-gray-500">歩数目安</p>
          <p class="mt-1 text-sm font-semibold text-emerald-600">
            {{ route.distance_km! * 1000 }}歩
          </p>
        </div>
        <div class="rounded-lg bg-white px-2 py-2 border border-gray-100">
          <p class="text-[11px] text-gray-500">所要時間</p>
          <p class="mt-1 text-sm font-semibold text-indigo-600">
            {{ route.duration_min }}分
          </p>
        </div>
      </div>
    </div>

    <!-- 見どころスポット -->
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <p class="text-sm font-semibold text-gray-800">見どころスポット</p>
        <p class="text-[11px] text-gray-500">
          全 {{ route.spots.length }} か所
        </p>
      </div>
      <ul class="space-y-1.5">
        <li
          v-for="(spot, index) in route.spots"
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
</template>
