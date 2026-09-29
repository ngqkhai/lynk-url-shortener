# ADR-003: Redis cache-aside cho redirect path

- **Trạng thái:** Accepted
- **Ngày:** 2026-09-22

## Quyết định

Redirect Service dùng Redis 8 standalone trong cùng Kubernetes cluster theo cache-aside. Key có dạng `redirect:v1:{shortCode}`, TTL tối đa 1 giờ và không vượt quá thời gian sống còn lại của URL. Redis không dùng persistence vì PostgreSQL read-model và URL Service mới là nguồn phục hồi dữ liệu.

Redis failure không làm request thất bại: service ghi structured warning rồi đọc PostgreSQL. Readiness chỉ báo Redis `degraded`, không loại pod khỏi traffic.

## Hệ quả

Cache có thể cold sau restart và request đầu tiên chậm hơn. Standalone Redis không phải cấu hình HA production; lựa chọn này phục vụ staging, benchmark và failure injection. Cache stampede protection và metrics chuyên sâu nằm ngoài Sprint 2.
