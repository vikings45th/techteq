export interface LatLng {
  lat: number;
  lng: number;
}

export interface ApiRequest {
  request_id: string;
  theme: string;
  distance_km: number;
  start_location: LatLng;
  end_location: LatLng;
  round_trip: boolean;
  debug: boolean;
}

export interface Route {
  route_id: string;
  polyline: LatLng[];
  distance_km: number;
  duration_min: number;
  title: string;
  summary: string;
  nav_waypoints: LatLng[];
  spots: { name?: string; type?: string }[];
}

export interface ApiResponse {
  statusCode: number;
  body: {
    request_id: string;
    route: Route;
    meta: any;
  };
}
