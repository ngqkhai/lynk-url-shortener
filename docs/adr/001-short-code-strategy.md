# ADR-001: NanoID Base62 cho short code

- **Trạng thái:** Accepted
- **Ngày:** 2026-09-16

## Quyết định

`url-service` dùng NanoID Base62 7 ký tự cho mã tự sinh. Unique constraint trong PostgreSQL là nguồn bảo đảm cuối cùng; khi va chạm, service tạo lại tối đa 5 lần. Custom alias có 3–32 ký tự Base62 và phân biệt hoa/thường.

## Lý do

Không cần sequence tập trung, mã không làm lộ số lượng URL đã tạo, và không có dependency hạ tầng mới. Không gian mã là `62^7`; retry xử lý an toàn collision hiếm gặp.

## Hệ quả

Mã không có thứ tự thời gian và phải xử lý unique violation khi ghi. Nếu retry hết, request lỗi thay vì trả một mã trùng.
