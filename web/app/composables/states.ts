import type { ApiRequest, Route } from '~/types/route';

export const useSearchParams = () => {
  return useState<ApiRequest>('searchParams', () => ({
    request_id: "initialSearchParamsStateRequestId",
    theme: 'exercise',
    distance_km: 5,
    start_location: { lat: 35.685175, lng: 139.752799 },
    end_location: { lat: 35.685175, lng: 139.752799 },
    round_trip: true,
    debug: false,
  }));
};

export const useCurrentRoute = () => {
  return useState<Route>('currentRoute', () => ({
    route_id: "initialRouteStateRequestId",
    polyline: [{ lat: 35.685175, lng: 139.752799 },{ lat: 35.685174, lng: 139.752798 }],
    distance_km: 5,
    duration_min: 30,
    title: "initialRouteStateTitle",
    summary: "initialRouteStateSummary",
    nav_waypoints: [{ lat: 35.685175, lng: 139.752799 },{ lat: 35.685174, lng: 139.752798 }],
    spots: [],
  }));
};