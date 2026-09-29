# ADR-002: 302 Found cho redirect

- **Trạng thái:** Accepted
- **Ngày:** 2026-09-16

## Quyết định

Endpoint `GET /:shortCode` trả `302 Found` với `Location` là URL gốc.

## Lý do

Đích của short URL có thể thay đổi trong tương lai và redirect tạm thời tránh browser/proxy cache vĩnh viễn như `301`. Link hết hạn trả `410 Gone`; mã không tồn tại trả `404 Not Found`.
