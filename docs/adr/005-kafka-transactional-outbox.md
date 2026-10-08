# ADR-005: Kafka KRaft và transactional outbox cho url.created

- Trạng thái: triển khai local trong Sprint 3A; staging chưa bật.
- Ngày: 2026-10-02.

## Bài toán

Redirect đang hydrate read model qua HTTP sau lần click đầu tiên. Cần đồng bộ URL mới trước click và giữ sự kiện khi broker unavailable. Ghi URL rồi publish trực tiếp có thể mất sự kiện nếu process chết giữa hai thao tác.

## Quyết định

URL Service commit `urls` và `url_outbox` trong cùng PostgreSQL transaction. Event envelope version 1 chứa eventId, thời gian UTC và URL/owner; Kafka key là shortCode. Không FK hoặc query sang database auth.

Worker claim tối đa 25 rows bằng `FOR UPDATE SKIP LOCKED`, lease 30 giây và owner UUID riêng mỗi batch. Publish với `acks=all`, deadline 10 giây; chỉ đánh dấu published khi lease còn hiệu lực. Thất bại giữ row, retry exponential 1–60 giây kèm jitter. Pending events không bị cleanup; published rows giữ 7 ngày. Crash sau broker acknowledgment có thể publish lại: semantics là **at least once**.

Consumer dùng request timeout 30 giây cho group synchronization/rebalance, tách DLQ producer timeout 2 giây. Chỉ vòng reconnect của ứng dụng quản lý restart; KafkaJS automatic restart tắt để tránh chồng cơ chế recovery. Session/rebalance timeout 30 giây, fetch wait tối đa 1 giây; GROUP_JOIN/crash được ghi bằng Pino.

Redirect Consumer group `lynk-redirect-v1` upsert vào `lynk_redirects`, warm Redis best effort, rồi commit offset thủ công. DB failure retry và giữ offset; malformed/unsupported event phải publish thành công vào `url.created.dlq` trước commit. Event hết hạn vẫn persist nhưng không warm cache. Duplicate upsert an toàn cho event tạo URL bất biến; cập nhật/xóa URL cần hợp đồng riêng trong sprint sau.

Local dùng image Apache `apache/kafka:4.2.2`, JVM/KRaft một broker+controller, heap 512 MiB, memory limit 1536 MiB và PVC 5 GiB. Topics `url.created`/`url.created.dlq`: 3 partitions, RF=1, retention 7 ngày; topic Job idempotent, auto-create disabled. Cluster ID ổn định khi restart. Services Kafka publish endpoint trước readiness để CLI probe dùng được advertised broker address.

`URL_EVENTS_ENABLED=false` trong staging; local bật. Kafka và consumer không tham gia readiness của HTTP API. Cold miss vẫn gọi URL internal HTTP, nên Kafka down không chặn tạo URL hoặc redirect khi các DB cần thiết còn hoạt động.

## Bằng chứng và giới hạn

[Acceptance và phép đo Sprint 3A](../experiments/02-sprint3a-auth-events.md) ghi kết quả thực. Test PostgreSQL xác nhận rollback URL khi outbox insert lỗi, collision không tạo orphan event, lease exclusion và reclaim không cho worker cũ ack. Compose kiểm tra broker outage/recovery, consumer DB failure, restart và DLQ.

Một broker RF=1 không cung cấp HA. PVC/retention có thể đầy nếu backlog kéo dài; vận hành phải theo dõi pending rows, oldest age và consumer lag. Chưa có số liệu Experiment B cho click analytics; `url.clicked`/analytics thuộc Sprint 3B.

## Nguồn

- [Apache Kafka Docker](https://kafka.apache.org/42/getting-started/docker/)
- [KafkaJS producing](https://kafka.js.org/docs/producing)
- [KafkaJS consuming](https://kafka.js.org/docs/consuming)
