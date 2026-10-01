# Runbook: Local Development Setup

Hướng dẫn thiết lập môi trường phát triển cục bộ từ đầu cho dự án **Lynk URL Shortener**.

---

## 📋 Yêu cầu tiên quyết (Prerequisites)

- **Operating System:** Linux / macOS / WSL2
- **Node.js:** `>= 22.0.0` (khuyên dùng v24.x LTS)
- **Docker:** `>= 24.x` & Docker Compose
- **kubectl:** `>= 1.28.x`
- **Helm:** `>= 3.12.x`
- **kind:** `>= 0.20.x` (cài đặt trước khi chạy script)

---

## ⚡ Khởi động nhanh (Quickstart)

### 1. Cài đặt Dependencies & Kiểm tra Code

```bash
# Cài đặt toàn bộ npm workspaces
make setup

# Chạy kiểm tra linter, typecheck và unit tests
make lint

# Chạy unit tests; CI tự bật PostgreSQL Testcontainers cho integration tests
make test
```

### 2. PostgreSQL và Redis local

```bash
make db-up
make db-migrate
make db-migrate-redirect
```

Sao chép `.env.example` thành `.env` (không commit file này), sau đó chạy service:

```bash
set -a; source .env; set +a
npm run dev --workspace=@lynk/url-service
```

Mở terminal thứ hai để chạy Redirect Service với database riêng:

```bash
set -a; source .env; set +a
PORT="$REDIRECT_PORT" DATABASE_URL="$REDIRECT_DATABASE_URL" \
  npm run dev --workspace=@lynk/redirect-service
```

Swagger UI có tại `http://localhost:3001/documentation` và `http://localhost:3002/documentation`.

### 3. Deploy toàn bộ phiên bản hiện tại vào local Kubernetes

Yêu cầu Docker đang chạy và tài khoản hiện tại có quyền dùng Docker socket. Lệnh dưới đây tạo hoặc dùng lại `kind` cluster, cài Traefik nếu thiếu, rồi triển khai vào namespace riêng `lynk-local`:

```bash
make k8s-local-deploy
```

Script tạo ba Secret trong cluster, hai PostgreSQL StatefulSet với PVC riêng và Redis 8 tạm thời. Sau đó script build hai Docker image từ working tree hiện tại, nạp image vào `kind`, chạy migration Job qua Helm `pre-install/pre-upgrade` hook và đợi hai Deployment sẵn sàng. Cuối cùng nó tạo một URL thử nghiệm và xác nhận redirect `302`.

Mỗi lần chạy sẽ dùng image tag mới để Pod nhận đúng code mới. Secret và PVC được dùng lại, không tự xóa dữ liệu. Nếu Secret database mất nhưng PVC còn, script dừng để tránh tạo mật khẩu mới không khớp database cũ. PVC giữ dữ liệu qua Pod restart, nhưng xóa cả cluster `kind` sẽ làm mất dữ liệu local.

Mỗi PostgreSQL local chỉ có một Pod. Trong lúc Pod này khởi động lại, các request cần database có thể lỗi tạm thời; đợi readiness trở lại trước khi kiểm tra dữ liệu. PVC giúp giữ dữ liệu, không cung cấp high availability.

### 4. Kiểm tra thủ công

```bash
kubectl -n lynk-local get pods,svc,pvc,jobs
curl -i --resolve lynk.localhost:80:127.0.0.1 http://lynk.localhost/health/ready
curl -i --resolve lynk.localhost:80:127.0.0.1 \
  -H 'content-type: application/json' \
  -d '{"originalUrl":"https://example.com","customAlias":"DemoLink"}' \
  http://lynk.localhost/api/v1/urls
curl -i --resolve lynk.localhost:80:127.0.0.1 http://lynk.localhost/DemoLink
```

Ingress chỉ nhận host `lynk.localhost` cho bản local. Lệnh `--resolve` đảm bảo `curl` trỏ tới `127.0.0.1` mà không cần sửa DNS. Helm local dùng namespace `lynk-local`; cluster kind không cài Argo CD hay tạo `lynk-staging`.

## Staging Kubernetes + Supabase

`kind` là môi trường local/integration, không dùng cho staging. Nếu triển khai staging trên một cluster khác, môi trường đó có thể dùng Argo CD, Redis 8 trong cluster và hai Supabase PostgreSQL database riêng. Người vận hành phải tạo các Secret trước khi sync; Argo CD chạy hai migration Job `PreSync`, và migration thất bại sẽ chặn rollout tương ứng.

### Redis failure test

Chỉ thực hiện trên staging test data:

```bash
argocd app set lynk-redis --sync-policy none
kubectl -n lynk-staging scale statefulset lynk-redis-master --replicas=0
BASE_URL=https://lynk.example.com TARGET_RPS=50 DURATION=60s \
  SUMMARY_PATH=results/redis-down.json k6 run benchmarks/k6-redirect.js
kubectl -n lynk-staging scale statefulset lynk-redis-master --replicas=1
argocd app set lynk-redis --sync-policy automated --self-heal --auto-prune
```

Xác nhận error rate bằng 0 trước khi ghi kết quả vào báo cáo experiment.

---

## 🎛️ Truy cập các bảng điều khiển (Dashboards)

| Công cụ             | Địa chỉ truy cập           | Ghi chú                       |
| :------------------ | :------------------------- | :---------------------------- |
| **Traefik Ingress** | `http://lynk.localhost`    | Cổng Ingress local, port 80   |

---

## 🧹 Dọn dẹp môi trường (Teardown)

Để xóa toàn bộ cluster `kind` và giải phóng tài nguyên:

```bash
make k8s-down
```
