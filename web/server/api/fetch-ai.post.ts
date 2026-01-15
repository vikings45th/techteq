interface ApiResponse {
  request_id: string;
  route: {
    route_id: string;
    polyline: string;
    distance_km: number;
    duration_min: number;
    summary: string;
    spots: Array<{ name?: string; type?: string }>;
  };
  meta: any;
}

// polylineデコード関数（Google Polyline Encoding Algorithm）
function decodePolyline(encoded: string): Array<{ lat: number; lng: number }> {
  const poly: Array<{ lat: number; lng: number }> = [];
  let index = 0;
  const len = encoded.length;
  let lat = 0;
  let lng = 0;

  while (index < len) {
    let b: number;
    let shift = 0;
    let result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    const dlat = ((result & 1) !== 0 ? ~(result >> 1) : (result >> 1));
    lat += dlat;

    shift = 0;
    result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    const dlng = ((result & 1) !== 0 ? ~(result >> 1) : (result >> 1));
    lng += dlng;

    poly.push({ lat: lat * 1e-5, lng: lng * 1e-5 });
  }

  return poly;
}

export default defineEventHandler(async (event) => {
  const requestBody = await readBody(event); //requestBody: jsonPayload,
  /*
    const jsonPayload = {
      request_id: crypto.randomUUID(),
      theme: theme.value,
      distance_km: distance.value,
      start_location: {
        lat: 35.6109,
        lng: 139.6263
      },
      round_trip: true,
      debug: false
    };
  */

  const apiUrl = "https://agent-203786374782.asia-northeast1.run.app/route/generate";
  try {
    // GETリクエスト
    const response = await $fetch<ApiResponse>(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: requestBody
    });

    // polylineをデコードして配列形式に変換
    const decodedPolyline = decodePolyline(response.route.polyline);

    // レスポンスにデコードされたpolylineを設定
    const processedResponse = {
      ...response,
      route: {
        ...response.route,
        polyline: decodedPolyline
      }
    };
    
    return {
      statusCode: 200,
      body: processedResponse
    };;
    
  } catch (error: any) {
    throw createError({
      statusCode: error.statusCode || 500,
      statusMessage: error.message || 'API呼び出しに失敗しました'
    });
  }
})