# Sprint 3A: Acceptance và phantom token latency

Ngày đo: 2026-10-02 (Asia/Bangkok). Phạm vi: local Docker Compose và kind; staging chưa bật. Kết quả dưới được đo/chạy thật, không dùng số liệu giả định.

## Implementation đã kiểm chứng

- Auth-service sở hữu PostgreSQL riêng, opaque access/refresh, Argon2id, rotation/reuse/logout và session revocation.
- Traefik ForwardAuth mTLS đổi opaque token thành RS256 JWT nội bộ; services verify chữ ký và owner. Không trả internal JWT ra client.
- Ownership nullable cho URL/read model; legacy URL vẫn public redirect.
- Transactional URL/outbox, leased dispatcher/retry, Kafka KRaft, consumer durable upsert/manual commit, DLQ và Redis best effort.
- Docker images non-root, migration Jobs độc lập, CI gateway e2e, Helm local on/staging off.

## Gates và failure evidence

| Gate / tình huống                           | Kết quả thực                                                                                                                                                                    |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| lint / build / format                       | Pass                                                                                                                                                                            |
| Full tests với `RUN_INTEGRATION_TESTS=true` | 37 tests pass; PostgreSQL/Redis Testcontainers thực, không skip integration                                                                                                     |
| Argon2 overload recovery sau thay đổi cuối  | Unit test pass: 2 active + 16 queued, request vượt giới hạn 503; dummy hash phục hồi sau overload                                                                               |
| Auth PostgreSQL                             | Normalize email, duplicate/wrong password, token hashes only, refresh concurrency/reuse commit revocation, normal rotation, logout, access/family expiry pass                   |
| Atomic outbox                               | Outbox insert lỗi rollback URL; conflict không có orphan event; two-worker lease exclusion/reclaim; stale owner không ack được                                                  |
| Ownership/compatibility                     | User B metadata 404; legacy metadata 404; public redirect còn 302; payload owner thiếu không xóa owner đã có trong read DB                                                      |
| Compose phantom                             | Opaque login -> me/create/metadata; no token/client JWT/forged headers bị từ chối; JWT không xuất hiện trong response headers                                                   |
| mTLS listener thật                          | Thiếu cert, sai CA, sai CN, expired client cert, sai server SAN bị từ chối; cert hợp lệ vẫn phải có opaque user token                                                           |
| Kafka trước first click                     | Redirect PostgreSQL đã có URL/owner trước request redirect đầu tiên                                                                                                             |
| Compose broker outage                       | POST 201 và pending outbox; HTTP cold miss 302; broker phục hồi -> published row + consumer sync                                                                                |
| Compose auth DB outage                      | Protected API 5xx; redirect public 302; auth DB phục hồi -> me 200                                                                                                              |
| Compose redirect DB outage                  | Source Kafka offsets không đổi khi DB down; DB phục hồi -> persist/commit; consumer restart tiếp tục sync                                                                       |
| Poison/duplicate                            | Invalid event DLQ ack, valid event kế tiếp cùng partition được xử lý; duplicate không tạo nhiều read rows                                                                       |
| kind deploy                                 | 3 Deployment ready, migration Jobs completed, Kafka/topics/PVC ready; gateway smoke pass                                                                                        |
| kind broker/auth outage                     | Pass: Kafka scale 0/1 giữ PVC, POST 201 pending outbox, HTTP cold miss 302, backlog published, consumer restart sync trước click, auth scale 0/1 fail closed và me phục hồi 200 |
| Runtime dependencies                        | `npm audit --omit=dev`: 0 vulnerabilities sau semver patches Fastify/fast-uri                                                                                                   |

Checkpoint bàn giao kind: cả 3 application Pods và Kafka ready; 3 migration Jobs và topic Job Complete; pending outbox = 0; consumer lag = 0 trên cả 3 partitions. Stack Compose test/volumes/temp keys đã dọn, kind/PVC/Secrets được giữ.

37 tests gồm auth 5, redirect 17, URL 14, shared 1. Test unit mặc định skip container tests; CI bật integration và có job Compose riêng. Development tooling còn 8 audit advisories (6 moderate, 2 high); không áp dụng force upgrade phá toolchain trong 3A.

## Phép đo k6

Lệnh tái lập:

```bash
LYNK_KEEP_STACK=true make test-sprint3a
# Dùng key directory được in ở cuối; đợi failure tests kết thúc.
LYNK_KEY_DIR=/tmp/lynk-compose-keys.<suffix> bash scripts/benchmark-phantom.sh
```

Môi trường đo: Docker runner Node 24.21.0, Fastify 5.12.5; Compose Traefik 3.5.0, Kafka 4.2.2, PostgreSQL 16 và Redis 8; k6 image 1.0.0. Kind dùng Traefik 3.7.13 (chart 41.5.0), được kiểm chứng riêng qua smoke/resilience.

Harness `benchmarks/k6-phantom.js` chạy 20 giây, 1 VU mỗi scenario cùng lúc:

1. `internal`: đọc owner metadata trực tiếp từ URL Service bằng internal JWT được harness nhận qua authenticated mTLS adapter.
2. `gateway`: đọc cùng URL qua Traefik bằng opaque access token; mỗi request introspect và JWT verify.

Backend/internal ports không publish ra host. TLS verify bật; client cert và CA mount read-only. Teardown logout benchmark session. Summary chỉ xuất metrics/checks/state, loại `setup_data` chứa tokens. Không đưa private key/token vào artifact.

| Đường đi                 | Requests | Median (ms) | Mean (ms) | p95 (ms) | p99 (ms) | Max (ms) |
| ------------------------ | -------: | ----------: | --------: | -------: | -------: | -------: |
| Internal JWT metadata    |    4.535 |        3,56 |      4,32 |     8,00 |    13,06 |   970,83 |
| Phantom gateway metadata |    1.534 |       11,47 |     13,39 |    22,55 |    32,68 |   976,84 |

- 6.069 metadata checks pass; failed checks = 0; HTTP error rate = 0 (k6 thresholds pass).
- Auth listener log count: trước 10, sau 1.546 -> **1.536 introspections**, đúng 1.534 gateway requests + 2 setup exchanges (create URL và nhận fixture JWT).
- p95 chênh khoảng 14,56 ms; median chênh khoảng 7,90 ms trong run này. Khác biệt bao gồm gateway routing, mTLS ForwardAuth, auth DB lookup/signing và downstream verification.

Artifacts: [k6 summary](results/sprint3a/phantom-summary.json), [introspection count](results/sprint3a/introspection-count.json).

Đây là một run ngắn trên máy local có cả kind và Compose. Hai scenario đồng thời có throughput khác nhau; max latency gần 1 giây ở cả hai đường. Chưa có profiling giải thích spikes hoặc repeated runs để thiết lập confidence interval. Kết quả không phải capacity/SLO của staging hay bằng chứng Experiment B. Giữ introspection không cache để có revocation ở request kế tiếp; optimization chỉ sau phép đo bổ sung và quyết định revocation window.

## Consumer recovery correction

Bài failure test kind ban đầu phát hiện sync sau restart mất hơn 120 giây. Broker logs ghi repeated rebalances; rows xuất hiện muộn, không mất dữ liệu. Consumer khi đó dùng request timeout 2 giây chung với producer, quá ngắn cho group synchronization, và KafkaJS automatic restart cùng vòng reconnect của app.

Đã tách consumer request timeout 30 giây khỏi DLQ producer 2 giây, session/rebalance 30 giây, fetch wait 1 giây; tắt KafkaJS automatic restart, dùng một vòng reconnect và thêm GROUP_JOIN/crash logs. Chạy lại cả Compose và kind resilience đều pass. Sau restart consumer trên kind, GROUP_JOIN logs ghi 190 ms rồi 9 ms khi nhận đủ partitions sau Pod cũ rời group. Đây là duration group join được instrument, không phải toàn bộ thời gian broker startup/recovery.

## Giới hạn và quan sát vận hành

- Local Kafka RF=1/PVC và auth một replica không có HA; staging activation cần rollout riêng.
- Traefik kind có thể mất thời gian cập nhật endpoints sau scale auth lên lại. Readiness Pod không đồng nghĩa request đầu tiên qua gateway đã recovery; acceptance đợi gateway me 200.
- ForwardAuth transport outage có thể chờ timeout của Traefik (đã quan sát context deadline); không hứa timeout 500 ms hoặc mọi lỗi là 503.
- KafkaJS 2.2.4 trên Node 24 phát `TimeoutNegativeWarning` ở client/admin calls do timer throttling của thư viện. Produce/consume/offset/DLQ/recovery gates vẫn pass; không suppress warning hoặc sửa dependency code.
- Chưa có analytics/click pipeline/Experiment B, distributed rate limits, email verification, automated key rotation hoặc observability sprint 4.
