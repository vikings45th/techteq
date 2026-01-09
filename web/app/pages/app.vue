<script setup>
  const moodItems = ref(['exercise', 'thinking', 'reflesh','nature']);
  const mood = ref('exercise');
  const distance = ref(5);

  const route = ref();
  const open = ref(false)

  const callApi = async()=> {
    try{
      const apiResponse = await $fetch("/api/fetch-ai", {//apiResponse={statusCode: 200,body: dummyRouteRes}
        method: "post",
        body: {mood: mood.value, distance: distance.value},
      });
      route.value = apiResponse.body;
      /*
        const dummyRouteRes = {
          mood : `${requestBody.mood}な気分`,
          title : "静寂のリバーサイドウォーク",
          polyline : [
            { lat: 37.772, lng: -122.214 },
            { lat: 21.291, lng: -157.821 },
            { lat: -18.142, lng: 178.431 },
            { lat: -27.467, lng: 153.027 },
          ],
          distance_km : requestBody.distance,
          duration_min : Math.round(requestBody.distance/0.06),
          steps : requestBody.distance*1000,
          summary : "信号の少ない川沿いの一本道。一定のリズムで歩くことで、頭の中を整理することができます。",
          spots : ["水面に映る夕日","長く続く遊歩道","静かな橋の下"]
        }
       */
      open.value = true;

    }catch(e){
      console.log(e);
    }
  }

  useHead({
    script: [
      {
        src: 'https://maps.googleapis.com/maps/api/js?key=AIzaSyAFhnRF8Mg46-4tlkOEWX0_0EG3Oy59Dz4&v=weekly',
        defer: true
      }
    ]
  })

  let mapInstance = null;

  function initMap() {
    const mapElement = document.getElementById("map");
    if (!mapElement || !window.google) {
      return;
    }

    // 既にマップが初期化されている場合は削除
    if (mapInstance) {
      mapInstance = null;
    }

    // ルートの座標を取得（デフォルト値は空配列）
    const coordinates = route.value?.polyline || [];

    // 中心点を計算（座標がある場合はその範囲、ない場合はデフォルト）
    let center = { lat: 0, lng: -180 };
    let zoom = 2;
    /*
    if (coordinates.length > 0) {
      // 座標の範囲を計算
      const lats = coordinates.map(c => c.lat);
      const lngs = coordinates.map(c => c.lng);
      center = {
        lat: (Math.max(...lats) + Math.min(...lats)) / 2,
        lng: (Math.max(...lngs) + Math.min(...lngs)) / 2
      };
      zoom = 10;
    }
    */

    mapInstance = new google.maps.Map(mapElement, {
      zoom: zoom,
      center: center,
      mapTypeId: "terrain",
    });

    if (coordinates.length > 0) {
      const flightPath = new google.maps.Polyline({
        path: coordinates,
        geodesic: true,
        strokeColor: "#FF0000",
        strokeOpacity: 1.0,
        strokeWeight: 2,
      });
      flightPath.setMap(mapInstance);
    }
  }

  // モーダルが開いた時にマップを初期化
  watch(open, (isOpen) => {
    if (isOpen && route.value) {
      // 次のティックでDOMが更新された後にマップを初期化
      nextTick(() => {
        // Google Maps APIが読み込まれるまで待つ
        const checkGoogleMaps = setInterval(() => {
          if (window.google) {
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
  });
</script>

<template>
  <div>
    <h1 class="mb-4">目的と距離に合わせてルートを提案します</h1>
    <p class="mb-4">気分を選ぶ</p>
    <URadioGroup indicator="hidden" v-model="mood" :items="moodItems" variant="card" class="mb-4"/>
    <div class="flex justify-between mb-4">
      <p>距離を選ぶ</p>
      <p>{{ distance }}km、{{ Math.round(distance/0.06) }}分、{{ distance*1000 }}歩</p>
    </div>
    <USlider v-model="distance" :min="0" :max="10" :step="0.5" :default-value="5" class="mb-4"/>
    <UButton color="secondary" label="ルートを生成" @click="callApi"/>
  </div>
  <UModal v-model:open="open">
    <template #content>
      <p>{{route.mood}}</p>
      <p>{{route.title}}</p>
      <div id="map" style="width: 100%; height: 400px;"></div>
      <p>{{ route.summary }}</p>
      <p>{{ route.distance_km }}km、{{  route.steps }}歩、{{ route.duration_min }}分</p>
      <p>見どころスポット</p>
      <ul>
        <li v-for="spot in route.spots" :key="spot">{{ spot }}</li>
      </ul>
    </template>
  </UModal>
</template>