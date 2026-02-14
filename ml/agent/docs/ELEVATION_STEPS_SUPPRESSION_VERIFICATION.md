# Elevation / Steps の外部API呼び出し抑制の確認

特徴量重要度 0% だった **elevation** と **steps** 取得のためだけに使っていた外部APIを、今回の変更で呼ばないようにしたことの確認用メモ。

## 1. コード上でどうなっているか

### Elevation API（Google Maps Elevation API）

- **変更前**: ルート候補ごとに `_calculate_elevation_gain(encoded, api_key)` を呼び、`https://maps.googleapis.com/maps/api/elevation/json` に **1リクエスト/ルート** 送っていた。
- **変更後**: `_calculate_elevation_gain` の**呼び出しを削除**済み。関数定義は残しているが、`compute_route_dests` と `compute_route_candidate` のどちらからも**一切呼ばれていない**。
- **返却**: `elevation_gain_m` は常に `0.0` を返す（BQ・下流互換のためキーは維持）。

→ **Elevation API への HTTP リクエストは発生していない。**

### Routes API（Directions / computeRoutes）の steps

- **変更前**: `X-Goog-FieldMask` に  
  `routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,routes.legs,routes.legs.steps,routes.legs.steps.navigationInstruction`  
  を指定し、**legs / steps をレスポンスに含めていた**（ペイロードが重い）。
- **変更後**: FieldMask を  
  `routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline`  
  のみに変更。**legs / steps は要求していない**（`compute_route_dests` と `compute_route_candidate` の両方で同じ）。

→ **Routes API へのリクエストは「steps なし」の最小フィールドのみ。steps 取得用のペイロード・処理は発生していない。**

### has_stairs

- steps を取得しなくなったため、階段判定も行っていない。返却は常に `has_stairs: False`（キーは互換のため維持）。

---

## 2. 本番ログで確認するには

**修正をデプロイしたあと**のリクエストでは、次のようになる想定です。

- **Elevation API**: Agent の Cloud Run ログに  
  `[Elevation API]` や `maps.googleapis.com/maps/api/elevation/json` が**出ない**。  
  （1日以内のログに同じメッセージが出ている場合は、**デプロイ前のリクエスト**の残り。）
- **Routes API**: 引き続き `routes.googleapis.com/directions/v2:computeRoutes` は呼ばれるが、FieldMask が最小になっているためレスポンスは軽い。

確認例（Agent の直近ログで Elevation が出ていないことの確認）:

```bash
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=agent' \
  --project=firstdown-482704 --limit=300 --format=json --freshness=1h \
  | grep -i "elevation" || echo "No Elevation API calls in last 1h"
```

デプロイ後 1 時間以内のログで `No Elevation API calls in last 1h` と出れば、その時間帯では Elevation は呼ばれていない。

---

## 3. まとめ

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| Elevation API 呼び出し | ルート数 N → N 回 | **0 回** |
| Routes API の steps/legs 要求 | あり（FieldMask に含む） | **なし（距離・時間・polyline のみ）** |
| has_stairs / elevation_gain_m | API から取得 | 常に False / 0.0（取得処理なし） |

期待どおり「elevation と steps の情報取得のための外部API呼び出しは抑制されている」状態になっている。
