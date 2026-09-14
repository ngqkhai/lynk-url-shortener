# Runbook: Local Development Setup

Hướng dẫn thiết lập môi trường phát triển cục bộ từ đầu cho dự án **Lynk URL Shortener**.

---

## 📋 Yêu cầu tiên quyết (Prerequisites)

* **Operating System:** Linux / macOS / WSL2
* **Node.js:** `>= 22.0.0` (khuyên dùng v24.x LTS)
* **Docker:** `>= 24.x` & Docker Compose
* **kubectl:** `>= 1.28.x`
* **Helm:** `>= 3.12.x`
* **kind:** `>= 0.20.x` (tự động cài đặt qua script nếu chưa có)

---

## ⚡ Khởi động nhanh (Quickstart)

### 1. Cài đặt Dependencies & Kiểm tra Code
```bash
# Cài đặt toàn bộ npm workspaces
make setup

# Chạy kiểm tra linter & typecheck
make lint

# Chạy toàn bộ Unit & Integration tests
make test
```

### 2. Khởi chạy Local Kubernetes Cluster (`kind`)
Lệnh này sẽ tự động:
1. Dựng cluster `lynk-cluster` với port mapping (80, 443, 8080).
2. Cài đặt **Traefik Ingress Controller** (NodePort 32080 / 32443).
3. Cài đặt **ArgoCD** (NodePort 32081).
4. Tạo namespace `lynk-staging`.

```bash
make k8s-up
```

### 3. Build & Nạp Docker Image vào Cluster cục bộ
```bash
# Build image url-service
make docker-build-url

# Nạp image vào kind cluster
kind load docker-image lynk-url-service:latest --name lynk-cluster
```

### 4. Triển khai ứng dụng qua Helm
```bash
helm upgrade --install lynk-services ./infra/k8s/helm/lynk-services \
  --namespace lynk-staging \
  --set urlService.image.repository=lynk-url-service \
  --set urlService.image.tag=latest \
  --set urlService.image.pullPolicy=Never
```

### 5. Kiểm tra kết nối qua Ingress
```bash
# Kiểm tra liveness probe qua Traefik Ingress
curl -i http://localhost/health

# Kiểm tra readiness probe qua Traefik Ingress
curl -i http://localhost/health/ready
```

---

## 🎛️ Truy cập các bảng điều khiển (Dashboards)

| Công cụ | Địa chỉ truy cập | Ghi chú |
| :--- | :--- | :--- |
| **Traefik Ingress** | `http://localhost` (Port 80) | Cổng Ingress điều hướng chính |
| **Traefik Dashboard** | `http://localhost:8080` | Giám sát routers & middlewares |
| **ArgoCD Web UI** | `http://localhost:32081` | Quản lý GitOps deployment |

### Lấy mật khẩu đăng nhập ban đầu của ArgoCD:
* **Username:** `admin`
* **Password:**
  ```bash
  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo ""
  ```

---

## 🧹 Dọn dẹp môi trường (Teardown)

Để xóa toàn bộ cluster `kind` và giải phóng tài nguyên:
```bash
make k8s-down
```
