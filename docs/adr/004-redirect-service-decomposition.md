# ADR-004: Tách Redirect Service và read-model riêng

- **Trạng thái:** Accepted
- **Ngày:** 2026-09-22

## Quyết định

Public `GET /:shortCode` được chuyển hoàn toàn sang Redirect Service để read path có thể tối ưu và scale độc lập. Service sở hữu database `lynk_redirects` và không truy vấn trực tiếp database `lynk_urls`.

Trong Sprint 2, Redis/DB miss gọi cluster-only `GET /internal/urls/:shortCode` của URL Service rồi upsert read-model và cache. Sprint 3 sẽ chủ động đồng bộ bằng event `url.created`; HTTP fallback vẫn được giữ cho cold miss.

## Hệ quả

Redirect vẫn hoạt động khi Redis lỗi và có thể phục vụ cache hit khi upstream chậm. Trước Kafka, URL mới chỉ xuất hiện trong read-model ở lần redirect đầu tiên. Internal API chưa có service authentication; endpoint không được expose qua Ingress và sẽ được harden ở Sprint 5.
