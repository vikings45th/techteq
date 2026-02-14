<script setup lang="ts">
import type { ApiRequest } from "~/types/route";
import { useRouteApi } from "~/composables/useRouteApi";
import { useGenerateRequestid } from "~/composables/useGenerateRequestid";
import {
  useSearchParams,
  useCurrentRoute,
  useQuickSearch,
} from "~/composables/states";

definePageMeta({
  layout: "app",
});

const { generateRequestid } = useGenerateRequestid();
const { fetchRoute } = useRouteApi();

const themeItems = ref([
  {
    label: "頭を休ませる",
    value: "think",
  },
  {
    label: "呼吸を整える",
    value: "nature",
  },
  {
    label: "気分転換をする",
    value: "refresh",
  },
  {
    label: "体を動かす",
    value: "exercise",
  },
]);

// 検索条件の初期値を作成
const searchParams = ref<ApiRequest>({
  request_id: "initialSearchParamsStateRequestId",
  theme: "exercise",
  distance_km: 2,
  start_location: { lat: 35.685175, lng: 139.752799 },
  end_location: { lat: 35.685175, lng: 139.752799 },
  round_trip: true,
  debug: false,
});

const locationError = ref<string | null>(null);
const loadingLocation = ref<boolean>(false);
const loadingApi = ref<boolean>(false);

const searchParamsState = useSearchParams();
const routeState = useCurrentRoute();
const quickSearchState = useQuickSearch();

// 現在地を保存する変数
const currentLocation = ref<{ lat: number; lng: number }>({
  lat: 35.685175,
  lng: 139.752799,
});

// 地図の中心位置（固定、変更しない）
const mapCenter = ref<{ lat: number; lng: number }>({
  lat: 35.685175,
  lng: 139.752799,
});

// マーカーとinterval IDを管理する変数
const startMarker = ref<any>(null);
const mapClickListener = ref<any>(null);
const markerDragendListener = ref<any>(null);
const mapInstance = ref<any>(null);

function destroyMap() {
  // イベントリスナーを削除
  if (mapClickListener.value && (window as any).google) {
    (window as any).google.maps.event.removeListener(mapClickListener.value);
    mapClickListener.value = null;
  }

  if (markerDragendListener.value && (window as any).google) {
    (window as any).google.maps.event.removeListener(
      markerDragendListener.value,
    );
    markerDragendListener.value = null;
  }

  // マーカーを削除
  if (startMarker.value) {
    // AdvancedMarkerElementの場合は、mapプロパティをnullに設定
    if (startMarker.value.map !== undefined) {
      startMarker.value.map = null;
    }
    // DOMから削除
    const mapElement = document.querySelector("gmp-map") as any;
    if (mapElement && startMarker.value.parentNode) {
      startMarker.value.remove();
    }
    startMarker.value = null;
  }

  // マップインスタンスをクリーンアップ
  if (mapInstance.value) {
    // マップ上のすべてのオーバーレイを削除
    if (mapInstance.value.overlayMapTypes) {
      mapInstance.value.overlayMapTypes.clear();
    }
    // マップインスタンスをnullに設定
    mapInstance.value = null;
  }

  // DOM要素の内容をクリア（必要に応じて）
  const mapElement = document.querySelector("gmp-map") as any;
  if (mapElement) {
    // マーカーなどの子要素を削除
    while (mapElement.firstChild) {
      mapElement.removeChild(mapElement.firstChild);
    }
  }
}

const fetchCurrentLocation = (): Promise<void> => {
  if (!navigator.geolocation) {
    locationError.value = "このブラウザは位置情報取得に対応していません。";
    return Promise.resolve();
  }

  loadingLocation.value = true;
  locationError.value = null;

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        currentLocation.value = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
        };
        // 現在地を取得したときは地図の中心も移動
        mapCenter.value = currentLocation.value;

        const mapElement = document.querySelector("gmp-map") as any;
        if (mapElement) {
          mapElement.zoom = 16;
          mapElement.center = {
            lat: mapCenter.value.lat,
            lng: mapCenter.value.lng,
          };

          // マーカーを更新
          if (startMarker.value) {
            startMarker.value.position = currentLocation.value;
          }
        }

        loadingLocation.value = false;
        resolve();
      },
      (err) => {
        loadingLocation.value = false;
        locationError.value = "位置情報の取得に失敗しました: " + err.message;
        resolve(); // エラー時も完了扱いにする
      },
      {
        enableHighAccuracy: true,
        timeout: 100000,
      },
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

  try {
    //検索条件を保存し、ルート検索
    searchParamsState.value = searchParams.value;
    const route = await fetchRoute(searchParams.value);

    //検索結果ルートを保存し、ルート画面に遷移
    routeState.value = route;

    // 遷移前にマーカーを削除
    destroyMap();

    await navigateTo(
      `/app/route?request_id=${searchParams.value.request_id}&route_id=${route.route_id}`,
    );
  } catch (e) {
    console.error(e);
  } finally {
    loadingApi.value = false;
  }
};

const initMap = async () => {
  const mapElement = document.querySelector("gmp-map") as any;

  if (!mapElement || !(window as any).google) {
    return;
  }

  // Dynamic Library Importを使用して必要なライブラリを読み込む
  const { Map } = await (window as any).google.maps.importLibrary("maps");
  const { AdvancedMarkerElement, PinElement } = await (
    window as any
  ).google.maps.importLibrary("marker");

  // 既にマップが初期化されている場合は削除
  if (mapInstance.value) {
    destroyMap();
  }

  mapElement.zoom = 16;
  mapElement.center = { lat: mapCenter.value.lat, lng: mapCenter.value.lng };
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

  // 歩いている人のSVGアイコンをData URLとして作成
  const walkingSvgString =
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24"><path fill="white" d="M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2s-2 .9-2 2s.9 2 2 2M9.8 8.9L7 23h2.1l1.8-8l2.1 2v6h2v-7.5l-2.1-2l.6-3C14.8 12 16.8 13 19 13v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1c-.3 0-.5.1-.8.1L6 8.3V13h2V9.6z"/></svg>';
  const walkingSvgDataUrl =
    "data:image/svg+xml," + encodeURIComponent(walkingSvgString);

  const startPin = new PinElement({
    scale: 1.5,
    background: "#FB7C2D",
    borderColor: "#FFFFFF",
    glyphSrc: walkingSvgDataUrl,
  });

  // 高度なマーカーを使用
  startMarker.value = new AdvancedMarkerElement({
    position: currentLocation.value,
    title: "スタート地点",
    gmpDraggable: true,
  });
  // Append the pin to the marker.
  startMarker.value.append(startPin);
  // Append the marker to the map.
  mapElement.append(startMarker.value);

  // マーカーがドラッグされたときに位置を更新
  markerDragendListener.value = startMarker.value.addListener("dragend", () => {
    const pos = {
      lat: startMarker.value.position.lat,
      lng: startMarker.value.position.lng,
    };
    currentLocation.value = pos;
  });

  // 地図がクリックされたときにもマーカーを移動
  // innerMap が実際の Google Maps Map オブジェクト
  mapClickListener.value = mapElement.innerMap.addListener(
    "click",
    (event: any) => {
      const lat = event.latLng.lat();
      const lng = event.latLng.lng();
      const pos = { lat, lng };
      startMarker.value.position = pos;
      currentLocation.value = pos;
    },
  );
};

onMounted(async () => {
  initMap();
  // quick_search=trueの場合は自動的に検索を実行
  if (quickSearchState.value.quick_search) {
    loadingApi.value = true;
    searchParams.value.theme = quickSearchState.value.theme;
    searchParams.value.distance_km = quickSearchState.value.distance_km;

    await fetchCurrentLocation();
    await callApi();
  } else {
    // 保存されている検索条件があれば、searchParamsに代入
    // request_idが初期値でない場合は、以前の検索条件が保存されていると判断
    const hasSavedSearchParams =
      searchParamsState.value &&
      searchParamsState.value.request_id !==
        "initialSearchParamsStateRequestId";

    if (hasSavedSearchParams) {
      searchParams.value = searchParamsState.value;
      // 保存されている検索条件の開始地点を現在地に設定
      currentLocation.value = { ...searchParams.value.start_location };
      // 地図の中心も設定
      mapCenter.value = { ...searchParams.value.start_location };
    } else {
      // 初回アクセスまたは初期値の場合は現在地を取得
      await fetchCurrentLocation();
    }

    // DOMが完全にレンダリングされた後に地図を初期化
    await nextTick();
  }
});

onBeforeUnmount(() => {
  // コンポーネントがアンマウントされる時にマップを破棄
  destroyMap();
  // quickSearchStateを初期値に戻す
  quickSearchState.value = {
    quick_search: false,
    theme: "think",
    distance_km: 2,
  };
});
</script>
<template>
  <div class="flex flex-col h-dvh">
    <!-- 開始地点の地図 -->
    <div class="flex-1 flex flex-col">
      <div class="relative flex-1 bg-gray-50">
        <gmp-map
          :center="mapCenter"
          :zoom="17"
          map-id="9153bea12861ba5a84e2b6d3"
          class="w-full h-full"
        ></gmp-map>
        <!-- 現在地を取得ボタン（地図右下に重ねて表示） -->
        <UButton
          size="xl"
          color="primary"
          icon="ic:baseline-my-location"
          :loading="loadingLocation"
          @click="fetchCurrentLocation"
          variant="outline"
          class="absolute bg-white bottom-6 right-6 p-3 shadow-lg z-10"
        />
      </div>
      <p class="text-xs text-gray-500 px-2 py-1">
        地図をクリックするか、マーカーをドラッグして開始地点を設定してください。
      </p>
    </div>
    <!-- フォーム部分（画面下部に固定） -->
    <div class="flex-none shrink-0 px-2 pb-2">
      <div class="pt-4 pb-4 mr-2 px-2">
        <URadioGroup
          indicator="hidden"
          orientation="horizontal"
          v-model="searchParams.theme"
          :items="themeItems"
          variant="card"
          :ui="{
            fieldset: 'grid grid-cols-2 gap-2',
          }"
        />
      </div>
      <div class="px-4">
        <USlider
          class="py-4"
          :min="1"
          :max="3"
          :step="0.5"
          v-model="searchParams.distance_km"
        />
        <div class="flex justify-between text-xs text-gray-500 mt-2 px-0.5">
          <span>15分</span>
          <span>30分</span>
          <span>45分</span>
        </div>
      </div>
      <UButton
        block
        color="primary"
        label="案内してもらう"
        class="my-4 text-lg font-bold rounded-full px-4"
        @click="callApi"
      />
    </div>
  </div>

  <!-- 検索中のモーダル -->
  <UModal
    v-model:open="loadingApi"
    :dismissible="false"
    title="条件に合う散歩ルートを探しています。"
    description="しばらくお待ちください。"
  >
    <template #content>
      <div class="flex flex-col items-center justify-center space-y-4 py-4">
        <UIcon
          name="i-heroicons-arrow-path"
          class="w-8 h-8 animate-spin text-primary-600"
        />
        <div class="text-center space-y-2">
          <p class="text-gray-600">条件に合う散歩ルートを探しています。</p>
          <p class="text-gray-600">しばらくお待ちください。</p>
        </div>
      </div>
    </template>
  </UModal>
</template>
