interface LatLng {
  lat: number;
  lng: number;
}

interface AgentResponse {
  request_id: string;
  route: {
    route_id: string;
    polyline: string;
    distance_km: number;
    duration_min: number;
    title: string;
    summary: string;
    nav_waypoints: LatLng[];
    spots: { name?: string; type?: string }[];
  };
  meta: any;
}

// polylineデコード関数（Google Polyline Encoding Algorithm）
function decodePolyline(encoded: string): LatLng[] {
  const poly: LatLng[] = [];
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
    const dlat = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lat += dlat;

    shift = 0;
    result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    const dlng = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lng += dlng;

    poly.push({ lat: lat * 1e-5, lng: lng * 1e-5 });
  }

  return poly;
}

export default defineEventHandler(async (event) => {
  const requestBody = await readBody(event); //requestBody: ApiRequest,
  /*
    interface ApiRequest {
      request_id: string;
      theme: string;
      distance_km: number;
      start_location: LatLng;
      end_location: LatLng;
      round_trip: boolean;
      debug: boolean;
    }
  */

  const apiUrl =
    "https://agent-203786374782.asia-northeast1.run.app/route/generate";
  try {
    // POSTリクエスト
    const response = await $fetch<AgentResponse>(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: requestBody,
    });

    // polylineをデコードして配列形式に変換
    const decodedPolyline = decodePolyline(response.route.polyline);

    // レスポンスにデコードされたpolylineを設定
    const processedResponse = {
      ...response,
      route: {
        ...response.route,
        polyline: decodedPolyline,
      },
    };

    return {
      statusCode: 200,
      body: processedResponse,
    };
  } catch (error: any) {
    throw createError({
      statusCode: error.statusCode || 500,
      statusMessage: error.message || "API呼び出しに失敗しました",
    });
  }
});
