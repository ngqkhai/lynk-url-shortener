# ADR-000: Walking Skeleton & Day-1 Continuous Delivery

* **Trạng thái:** Accepted
* **Ngày quyết định:** 2026-09-14
* **Tác giả:** Solo Developer (@ngqkhai)
* **Phạm vi:** Hạ tầng phát triển, CI/CD, Containerization, Kubernetes Staging

---

## 1. Bối cảnh & Bài toán (Context & Problem Statement)

Trong quy trình phát triển phần mềm truyền thống, việc thiết lập CI/CD, Containerization, Kubernetes và cấu hình môi trường triển khai thường bị trì hoãn tới các giai đoạn cuối của dự án. Điều này dẫn tới:
1. **"Works on my machine" syndrome:** Ứng dụng chạy tốt trên máy cá nhân nhưng gặp lỗi khi đóng gói vào container hoặc deploy lên Kubernetes.
2. **Tích hợp muộn (Big Bang Integration):** Tốn rất nhiều thời gian giải quyết xung đột cấu hình, mạng, biến môi trường và security constraints khi chuẩn bị release.
3. **Thiếu khả năng phản hồi liên tục:** Không kiểm chứng được quy trình release và observability ngay từ các commit đầu tiên.

---

## 2. Quyết định (Decision)

Chúng tôi quyết định áp dụng nguyên tắc **"Walking Skeleton & Day-1 Continuous Delivery"** ngay từ **Sprint 0**:

1. **Walking Skeleton:** Xây dựng một microservice tối thiểu (`url-service` với endpoint `/health`) có đầy đủ các lớp kỹ thuật:
   - TypeScript ESM + Fastify.
   - Type-safe configuration qua Zod.
   - Unit & Integration testing qua Vitest.
   - Multi-stage Dockerfile chạy non-root user (`node:node`, uid: 1000).
2. **Kubernetes Staging Cục bộ (`kind`):**
   - Khởi tạo local cluster Kubernetes `kind` với Ingress mapping cổng `80` và `443`.
   - Triển khai **Traefik Ingress Controller** làm cổng vào duy nhất.
3. **Tự động hóa CI/CD & GitOps:**
   - **GitHub Actions:** Tự động chạy Linter, Tests, build Docker multi-stage và đẩy lên **GitHub Container Registry (`ghcr.io`)**.
   - **ArgoCD:** Cài đặt trực tiếp trên cluster để thực hiện GitOps reconciliation từ Helm Chart (`infra/k8s/helm/lynk-services`).

---

## 3. Các phương án thay thế đã xem xét (Alternatives Considered)

| Phương án | Ưu điểm | Nhược điểm / Lý do từ chối |
| :--- | :--- | :--- |
| **Chỉ dùng Docker Compose** | Cực kỳ nhẹ, dễ cấu hình ban đầu. | Không mô phỏng được các khái niệm cốt lõi của Kubernetes (Pods, Services, Ingress, Probes, Resource limits, HPA). |
| **Cloud Managed K8s (EKS/GKE)** | Giống môi trường production thật $100\%$. | Tốn chi phí điện toán đám mây cho dự án cá nhân; `kind` đáp ứng đủ $100\%$ API Kubernetes chuẩn mà hoàn toàn miễn phí. |
| **Push-based CI/CD (kubectl apply từ CI)** | Đơn giản, không cần cài ArgoCD. | Dễ gây tình trạng configuration drift, thiếu cơ chế self-healing tự động của GitOps. |

---

## 4. Hệ quả & Đánh giá (Consequences)

### Tích cực (Pros):
* Mọi dòng code mới từ Sprint 1 trở đi đều được kiểm thử và tự động triển khai lên Kubernetes ngay lập tức.
* Đảm bảo tính bảo mật từ ngày đầu (containers chạy non-root, Docker image tối giản).
* Tạo nền tảng đo lường benchmark và observability chuẩn xác trên môi trường Kubernetes thực tế.

### Tiêu cực (Cons & Mitigations):
* Cần tài nguyên RAM cho cụm `kind`, Traefik và ArgoCD (khoảng $\approx 1.5 - 2\text{GB}$ RAM).
* *Giải pháp giảm tải:* Giới hạn resource requests/limits cho từng component hạ tầng.
