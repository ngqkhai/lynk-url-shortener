# Experiment 01 — PostgreSQL-only vs Redis cache-aside

## Mục tiêu

Đo ảnh hưởng thực tế của Redis đến redirect latency và throughput trên cùng Kubernetes staging deployment, cùng resource limits và Supabase read-model database.

## Phương pháp

- Dataset: 1.000 URL còn hiệu lực, được hydrate trước mỗi lần đo.
- Tải: 100, 250, 500 và 1.000 RPS; 60 giây/mức; chạy 3 lần/cấu hình.
- Baseline: `CACHE_ENABLED=false`.
- Cache: `CACHE_ENABLED=true`, Redis warm.
- Thu thập: actual RPS, error rate, p50/p95/p99, Redis `keyspace_hits`/`keyspace_misses`, CPU và memory từ metrics API.
- Không so sánh các lần chạy khác image SHA, resource limits, region hoặc dataset.

```bash
BASE_URL=https://lynk.example.com TARGET_RPS=500 DATASET_SIZE=1000 \
  SUMMARY_PATH=results/db-only-500-1.json k6 run benchmarks/k6-redirect.js
```

Lặp lại với bốn mức RPS và ba lần chạy cho từng trạng thái cache. Trước cấu hình warm-cache, xóa cache benchmark rồi để `setup()` hydrate lại toàn bộ dataset.

## Kết quả

> Chỉ điền kết quả sau khi chạy trên staging. Không sử dụng số giả định.

| Cấu hình         | Target RPS | Actual RPS |       p50 |       p95 |       p99 | Error rate | Redis hit ratio |       CPU |    Memory |
| :--------------- | ---------: | ---------: | --------: | --------: | --------: | ---------: | --------------: | --------: | --------: |
| PostgreSQL-only  |  _pending_ |  _pending_ | _pending_ | _pending_ | _pending_ |  _pending_ |             N/A | _pending_ | _pending_ |
| Redis warm cache |  _pending_ |  _pending_ | _pending_ | _pending_ | _pending_ |  _pending_ |       _pending_ | _pending_ | _pending_ |

## Redis failure test

1. Warm toàn bộ dataset và xác nhận redirect 302.
2. Pause auto-sync của ArgoCD Application `lynk-redis`.
3. Scale Redis StatefulSet về 0 replica.
4. Chạy script ở 50 RPS trong 60 giây; yêu cầu không có 5xx và redirect tiếp tục từ PostgreSQL.
5. Restore 1 replica, resume auto-sync và xác nhận readiness báo Redis `ready`.

Ghi latency/error thực tế và log warning vào phần này sau khi chạy.
