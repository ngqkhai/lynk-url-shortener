# ADR-006: Phantom token, session revocation và URL ownership

- Trạng thái: triển khai local trong Sprint 3A; staging chưa bật.
- Ngày: 2026-10-02.

## Bài toán

URL metadata cần phân quyền theo owner. Client không cần đọc claims nội bộ; logout/reuse cần chặn token ở lần protected request tiếp theo. JWT tự chứa ở client sẽ cần chấp nhận cửa sổ revocation hoặc thêm denylist.

## Quyết định

`auth-service` TypeScript/Fastify sở hữu `lynk_auth`, public listener 3004 và private mTLS listener 3005. Register/login/refresh/logout là public; `/auth/me` và `/api/v1/urls` đi qua Traefik ForwardAuth. Redirect public không introspect.

Client nhận opaque `at_`/`rt_` với 32 byte CSPRNG; DB chỉ lưu SHA-256 hash. Access hạn 15 phút, session family hạn tuyệt đối 30 ngày. Refresh rotation lock row family rồi kiểm tra lại token: token consumed bị reuse sẽ revoke family trong transaction; lỗi 401 được ném **sau commit**. Refresh bình thường giữ access cũ đến expiry; logout/reuse chặn mọi access trong family ở lần introspection sau.

ForwardAuth gọi `GET /internal/auth/forward` bằng certificate CA local, CN `lynk-traefik`. Adapter chỉ có trên HTTPS 3005, kiểm tra certificate chain và CN, không route public và không sử dụng identity headers do client gửi. CA private key không mount vào Traefik hoặc auth-service. Đây là adapter của gateway, chưa phải OAuth provider/RFC 7662 endpoint đầy đủ.

Introspection thành công trả internal RS256 JWT qua response Authorization cho Traefik thay request header. Claims gồm sub/sid/atid/jti/kid, iss `lynk-auth`, aud `lynk-api`, exp tối đa 60 giây và không vượt access/family expiry. URL Service vẫn verify chữ ký/algorithm/claims/expiry locally. JWT hoặc refresh token gửi qua public protected route bị adapter từ chối. JWT không được trả ra client.

3A không cache authorization. Auth DB/service outage gây 5xx ở protected routes; redirect public vẫn hoạt động. Request đã introspect trước revocation có thể hoàn tất. Network error code/timeout phụ thuộc Traefik; không hứa mọi lỗi là 503 hoặc timeout 500 ms.

Password dùng Argon2id memory 19456 KiB, timeCost 2, parallelism 1; 2 thao tác song song, queue 16, quá tải 503. Email trim/lowercase, password 12–128 ký tự không trim. Rate limit mỗi pod theo socket IP: register 5, login 10, refresh 60 mỗi phút. Một Traefik có thể gom nhiều users vào cùng IP; distributed/per-client rate limiting còn là hardening sau.

URL `owner_id UUID NULL`: tạo mới lấy sub từ JWT, không tin owner do client gửi. Public metadata của URL thiếu, vô chủ hoặc owner khác đều 404. Legacy URLs vẫn redirect; không claim. Read model/cache thêm owner, payload cũ thiếu owner hiểu null; upsert null không xóa owner đã có. Không có FK cross-database.

## Hệ quả

Mỗi protected request thêm mTLS request, DB lookup và JWT signing; [k6 evidence](../experiments/02-sprint3a-auth-events.md) đo chi phí local. Auth trở thành dependency của protected APIs. Không đưa Redis token cache vào khi chưa có benchmark và quyết định revocation window.

Chưa có email verification, reset password, frontend/cookie flow, automatic key rotation hoặc auth HA. Secret và database PVC phải được phục hồi cùng identity hiện có khi redeploy. Staging flags tắt và không bị bật bởi CI image-tag update.

## Nguồn

- [Phantom token flow](https://curity.io/resources/learn/integration-other-phantom-token/)
- [Traefik ForwardAuth](https://doc.traefik.io/traefik/v3.5/reference/routing-configuration/http/middlewares/forwardauth/)
- [Refresh replay detection, RFC 9700 §4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14)
- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
