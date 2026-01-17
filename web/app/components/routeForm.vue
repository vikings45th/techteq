<script setup lang="ts">
  import type { ApiRequest } from '~/types/route';

  const props = defineProps<{
    detailed: boolean;
    jsonpayload : ApiRequest;
    loading?: boolean;
  }>();

  const themeItems = ref(['exercise', 'think', 'refresh', 'nature']);
  const currentLat = ref<number>(35.685175);
  const currentLng = ref<number>(139.752799);
  const startLat = ref<number>(35.685175);
  const startLng = ref<number>(139.752799);
  const endLat = ref<number>(35.685175);
  const endLng = ref<number>(139.752799)

  const locationError = ref<string | null>(null);
  const loadingLocation = ref(false);
    
  const emit = defineEmits<{
    'submit-request': [request: ApiRequest];
  }>();

  const handleSubmit = () => {
    endLat.value = startLat.value;
    endLng.value = startLng.value;

    props.jsonpayload.start_location = {lat: startLat.value, lng:startLng.value};
    props.jsonpayload.end_location = {lat: endLat.value, lng:endLng.value};

    //現状startとendの位置は一致させてる。
    //round_tripの計算: 緯度 0.001° ≒ 111m、経度 0.001° ≒ 91m
    //const flag:boolean = Math.abs(startLat.value - endLat.value) < 0.001 && Math.abs(startLng.value - endLng.value) < 0.001;
    //props.jsonpayload.round_trip = flag;

    emit('submit-request', props.jsonpayload);
  };

  onMounted(async() => {
    await fetchCurrentLocation();
  })

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
          currentLat.value = pos.coords.latitude;
          currentLng.value = pos.coords.longitude;
          loadingLocation.value = false;

          startLat.value = currentLat.value;
          startLng.value = currentLng.value;
          endLat.value = currentLat.value;
          endLng.value = currentLng.value;

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
</script>
  
<template>
  <div class="route-form space-y-6">
    <div class="space-y-2">
      <p class="text-sm font-semibold text-gray-700 tracking-wide">どんな気分？</p>
      <p class="text-xs text-gray-500">いまの気分に一番近いものを選んでください。</p>
    </div>
    <URadioGroup 
      indicator="hidden" 
      v-model="props.jsonpayload.theme" 
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
          {{ props.jsonpayload.distance_km }}km
        </p>
        <p class="text-gray-500">
          約 {{ Math.round(props.jsonpayload.distance_km/0.06) }} 分
        </p>
        <p class="text-gray-400">
          約 {{ props.jsonpayload.distance_km*1000 }} 歩
        </p>
      </div>
    </div>
    <USlider 
      v-model="props.jsonpayload.distance_km" 
      :min="0.5" 
      :max="10" 
      :step="0.5" 
      :default-value="5" 
      class="mb-2"
    />
    <div v-if="props.detailed">
      <div class="space-y-2 mb-2">
        <p class="text-sm font-semibold text-gray-700 tracking-wide">どこからどこまで？</p>
        <p class="text-xs text-gray-500">現在地をもとに開始地点と終了地点を指定します。</p>
      </div>
      <UButton
          size="xs"
          color="primary"
          :loading="loadingLocation"
          @click="fetchCurrentLocation"
      >
        現在地を取得
      </UButton>
      <!-- 開始地点・終了地点 -->
      <UInput
        v-model.number="startLat"
        type="number"
        step="0.000001"
        placeholder="開始地点の緯度"
      />
      <UInput
        v-model.number="startLng"
        type="number"
        step="0.000001"
        placeholder="開始地点の経度"
      />
      <UButton 
        color="secondary"
        label="ルートを生成"
        :loading="props.loading"
        class="w-full mt-2"
        @click="handleSubmit"
      />
    </div>
  </div>
</template>