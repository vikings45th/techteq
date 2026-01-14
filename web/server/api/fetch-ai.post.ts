export default defineEventHandler(async (event) => {
  const requestBody = await readBody(event); //requestBody: {mood: mood.value, distance: distance.value},

  const examplePolylines =[
    [
      { lat: 35.6109, lng: 139.6263 }, // 二子新地駅 周辺
      { lat: 35.6088, lng: 139.6224 }, // 多摩川河川敷（兵庫島付近）
      { lat: 35.6066, lng: 139.6298 }, // 二子玉川公園 付近
      { lat: 35.6094, lng: 139.6329 }, // 二子玉川駅 東側
    ],
    [
      { lat: 35.6319, lng: 139.6471 }, // 桜新町駅 周辺
      { lat: 35.6294, lng: 139.6425 }, // 呑川緑道 付近
      { lat: 35.6268, lng: 139.6463 }, // 弦巻方面の住宅街
      { lat: 35.6299, lng: 139.6508 }, // 桜新町商店街 南側
    ],
    [
      { lat: 35.7296, lng: 139.7910 }, // 三ノ輪駅 周辺
      { lat: 35.7279, lng: 139.7864 }, // 都電荒川線 三ノ輪橋付近
      { lat: 35.7258, lng: 139.7899 }, // 荒川区役所前方面の住宅街
      { lat: 35.7282, lng: 139.7945 }, // 日本堤二丁目 周辺
    ],
    [
      { lat: 35.6578, lng: 139.6849 }, // 駒場東大前駅 周辺
      { lat: 35.6599, lng: 139.6812 }, // 駒場野公園 付近
      { lat: 35.6565, lng: 139.6793 }, // 旧前田家本邸（外周）付近
      { lat: 35.6548, lng: 139.6836 }, // 駒場住宅街 南側
    ],
    [
      { lat: 35.7061, lng: 139.7596 }, // 本郷三丁目駅 周辺
      { lat: 35.7089, lng: 139.7615 }, // 東京大学 赤門 付近
      { lat: 35.7106, lng: 139.7583 }, // 東大構内（安田講堂方面）
      { lat: 35.7075, lng: 139.7560 }, // 春日通り 裏手
    ],
  ]

  const randomPolyline = examplePolylines[Math.floor(Math.random() * examplePolylines.length)]
  
  const dummyRouteRes = {
    mood : `${requestBody.mood}な気分`,
    title : "静寂のリバーサイドウォーク",
    polyline: randomPolyline,
    distance_km : requestBody.distance,
    duration_min : Math.round(requestBody.distance/0.06),
    steps : requestBody.distance*1000,
    summary : "信号の少ない川沿いの一本道。一定のリズムで歩くことで、頭の中を整理することができます。",
    spots : ["水面に映る夕日","長く続く遊歩道","静かな橋の下"]
  }
  

  return {
    statusCode: 200,
    body: dummyRouteRes,
  }
})