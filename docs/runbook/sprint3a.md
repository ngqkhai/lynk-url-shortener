# Runbook Sprint 3A: Auth, phantom token và URL events

## Chạy và kiểm tra

```bash
npm ci
npm run lint
npm run build
RUN_INTEGRATION_TESTS=true npm test  # cần Docker socket; không skip PostgreSQL/Redis tests
make test-sprint3a                  # Compose riêng, gateway mTLS + Kafka + failure tests
make k8s-local-deploy               # local kind, namespace lynk-local, giữ PVC/Secrets
```

Compose test build ba images và mở gateway tại `127.0.0.1:8088`. Backends/internal listener không publish host ports. Profile `gateway` dùng file provider; kind dùng Kubernetes Middleware CRD và Ingress. Test mặc định dọn stack/volume/temp keys khi kết thúc. Dùng project name riêng cho mỗi concurrent run; `LYNK_GATEWAY_PORT` và `LYNK_BASE_URL` phải khớp khi đổi cổng.

```bash
LYNK_KEEP_STACK=true make test-sprint3a
# Cuối output có đường dẫn temp keys để chạy thêm checks/benchmark.
```

Không dùng `LYNK_COMPOSE_PROJECT` trỏ vào stack có dữ liệu cần giữ: test cố ý stop/restart broker và DB, mặc định xóa volumes của project đó. Kind deploy không chạy failure test phá kết nối DB; smoke dùng dữ liệu có suffix riêng và giữ dữ liệu local.

## API qua kind

```bash
curl --resolve lynk.localhost:80:127.0.0.1 -sS \
  -H 'content-type: application/json' \
  -d '{"email":"owner@example.com","password":"your-long-local-password"}' \
  http://lynk.localhost/api/v1/auth/register

# Lưu token trong memory của shell; không ghi vào repo hoặc logs.
token_pair=$(curl --resolve lynk.localhost:80:127.0.0.1 -sS \
  -H 'content-type: application/json' \
  -d '{"email":"owner@example.com","password":"your-long-local-password"}' \
  http://lynk.localhost/api/v1/auth/login)
ACCESS_TOKEN=$(printf '%s' "$token_pair" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
REFRESH_TOKEN=$(printf '%s' "$token_pair" | python3 -c 'import json,sys; print(json.load(sys.stdin)["refreshToken"])')

curl --resolve lynk.localhost:80:127.0.0.1 -sS \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://lynk.localhost/api/v1/auth/me
curl --resolve lynk.localhost:80:127.0.0.1 -sS \
  -H 'content-type: application/json' -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"originalUrl":"https://example.com","customAlias":"DemoOwned"}' \
  http://lynk.localhost/api/v1/urls
curl --resolve lynk.localhost:80:127.0.0.1 -i http://lynk.localhost/DemoOwned
```

`/auth/me` trả `{user: {id,email,createdAt}}`; login/refresh trả opaque token pair. Refresh/logout body `{refreshToken}`. Serialize refresh trên client: reuse token cũ, kể cả hai refresh đồng thời, revoke family. Logout idempotent 204. Metadata URL của owner khác/vô chủ trả 404; redirects vẫn public. `/internal/*` không có public route; private adapter 3005 cần mTLS và token user.

## Failure tests trên kind

Sau `make k8s-local-deploy`, có thể chạy kiểm tra broker/PVC, outbox và auth outage trên namespace local:

```bash
python3 scripts/test-kind-resilience.py
```

Script dùng URL/account suffix riêng, scale Kafka và auth-service xuống 0 rồi khôi phục 1 replica, restart redirect consumer. Đây là kiểm tra có chủ ý làm gián đoạn local APIs trong vài phút; không chạy trên staging hoặc lúc người khác đang dùng cluster.

## Local identity và migrations

Kind script generate RSA signing keys và CA/server/client certificates trong `/tmp`, đưa đúng leaf material vào Secrets, rồi xóa temp directory. CA private key không mount vào app/gateway. JWT Secret được reuse. Nếu mất database/JWT Secret nhưng PVC còn, phục hồi Secret gốc trước redeploy; không tự sinh identity mới. Cert local có hạn 365 ngày; rotate leaf certs qua Secret update và restart auth/Traefik trước expiry. Automated rotation ngoài 3A.

Migration CLI chỉ cần DATABASE_URL. Helm hooks `pre-install/pre-upgrade` và ArgoCD `PreSync` chạy standalone Jobs. Schema thêm nullable owners và bảng outbox, giữ URL cũ tương thích. Staging `AUTH_REQUIRED=false`, events false, auth/phantom disabled; image tag update không kích hoạt tính năng.

Kafka local là StatefulSet, một broker/controller, RF=1, không có HA. Không public broker qua Ingress. Headless/bootstrap Services publish endpoints trước readiness để Kafka CLI probe không tự chặn advertised address.

## Kiểm tra backlog, lag và lỗi

```bash
kubectl -n lynk-local get pods,pvc,jobs,middleware
kubectl -n lynk-local logs deployment/url-service --tail=50
kubectl -n lynk-local logs deployment/redirect-service --tail=50
kubectl -n lynk-local exec url-postgres-0 -- psql -U lynk -d lynk_urls -c \
  "select count(*) as pending, min(created_at) as oldest from url_outbox where published_at is null"
kubectl -n lynk-local exec kafka-0 -- /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 --group lynk-redirect-v1 --describe
```

Pending rows không bị discard. Worker claim batch 25, lease 30s, retry 1–60s; published cleanup 7 ngày. Nếu backlog vượt broker retention/read model thiếu rows, dùng internal HTTP fallback cho click và lập replay/reconciliation riêng trước khi xóa outbox. Không xóa hoặc reset offset để che lỗi.

Consumer group synchronization timeout 30s tách khỏi DLQ producer 2s; vòng reconnect duy nhất, GROUP_JOIN/crash logs giúp thấy recovery và assignment. HTTP readiness không đợi Kafka group join.

Poison event DLQ có raw input, source partition/offset và reason; chỉ commit source khi DLQ ack thành công. DB failure giữ offset; Redis failure vẫn commit sau DB. `make test-sprint3a` xác nhận các hành vi này trên stack cô lập.

Auth DB/service unavailable: protected APIs trả 5xx, public redirect/health vẫn chạy. Auth DB lookup có connect/statement timeout; ForwardAuth transport timeout do Traefik quản lý. Rate limits per-pod/socket IP có thể gom nhiều users sau gateway. Đây là giới hạn local được ghi ở ADR-006.

## Benchmark

[Evidence Sprint 3A](../experiments/02-sprint3a-auth-events.md) ghi kết quả local. Khi Compose stack được giữ và failure tests đã kết thúc:

```bash
LYNK_KEY_DIR=/tmp/lynk-compose-keys.<suffix> bash scripts/benchmark-phantom.sh
```

Script dùng k6 image 1.0.0, CA/mTLS verification bật, chạy 20 giây với 1 VU cho mỗi đường đi; summary ở `/tmp/lynk-3a-benchmark/phantom-summary.json` chỉ có metrics, không có token-bearing setup data. Teardown logout benchmark session.

Redirect benchmark dùng `AUTH_REQUIRED=true AUTH_EMAIL=... AUTH_PASSWORD=...` cho setup login/refresh; redirect iterations vẫn public. Không đưa password/token vào summary hoặc commit shell history.
