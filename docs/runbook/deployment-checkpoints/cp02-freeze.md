# CP02 — Freeze legacy CD và ranh giới kiểm tra

CP02 giữ ứng dụng đang chạy, chặn delivery tự động trong migration và tách source/infrastructure/GitOps checks. Theo yêu cầu mới của người học, chỉ commit/push branch `checkpoint/cp02-freeze-legacy` để chạy CI, **không tạo PR, không merge**. Chỉ làm CP03 khi người học nói “tiếp”.

## Trạng thái trước và thay đổi live

Preflight ngày 2026-10-09 UTC (2026-10-10 Asia/Bangkok): không có Actions run chưa completed trong inventory đã đọc; SSM list-commands của instance `i-03bb7dcb94ec8bd21` không có Pending/InProgress/Delayed/Cancelling. CP01 CI run 37999017653 đã success. Không hủy runner/command hoặc đụng workload đang chạy.

Environment `aws-demo` trước đây chỉ có custom branch policy `main`, admin bypass=true, không required reviewer. Repository chưa có biến `LYNK_DEPLOY_MODE`.

Thay đổi đã áp dụng qua GitHub API:

- `aws-demo`: reviewer `ngqkhai` (user ID 92835482), admin bypass=false, wait_timer=0; giữ custom branch policy `main` (ID 62413507).
- `prevent_self_review=false`: một operator duy nhất vẫn có thể tự phê duyệt khi chủ động khôi phục SSM về sau. Trong migration không phê duyệt các pending legacy deploy jobs.
- Repository variable `LYNK_DEPLOY_MODE=paused`. Đây là cấu hình không bí mật.

[Bằng chứng gate trước/sau](evidence/cp02-freeze.json) chỉ chứa metadata; không có credential/token. API gate theo [GitHub environment documentation](https://docs.github.com/en/rest/deployments/environments).

**Ranh giới quan trọng:** workflow mới đang ở branch, chưa có trên `main`. Repository variable chưa được workflow cũ đọc; live freeze của workflow cũ dựa vào reviewer gate `aws-demo`, trước khi job lấy AWS credentials. Khi source CP02 vào main bằng quy trình operator sau này, mode guard mới có hiệu lực trên main. Không nói rằng thay variable đã sửa source main.

## Diff workflow

| Thành phần                 | CP02                                                                                                                                      |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| CI triggers                | Giữ push/PR main; thêm push `checkpoint/**` để học và chạy CI không cần PR                                                                |
| Source checks              | Lint/format/build/application tests, failure scenarios và gateway/Kafka E2E vẫn chạy khi paused                                           |
| Infrastructure checks      | Ansible syntax, CloudFormation lint, shell syntax, Helm lint; thêm workflow gate matrix tests                                             |
| GitOps checks              | Job riêng kiểm tra Application identities/source/chart/value-file references bằng PyYAML 6.0.3; không apply hoặc tuyên bố cluster Healthy |
| Mode policy                | Job read-only, không có id-token permission; missing/empty=paused; chỉ nhận paused/ssm/argocd; typo hoặc output injection làm policy fail |
| CI legacy deployment       | Chỉ push main với policy output=ssm; paused/argocd không gọi reusable deploy workflow                                                     |
| Manual/reusable deployment | Kiểm tra policy riêng, chỉ main push/dispatch với mode=ssm; guard `--require-ssm` trước AWS credentials; giữ environment aws-demo         |
| Publication                | Vẫn chỉ main push và sau các checks; paused không dừng build/publish. Path filters và artifact redesign thuộc CP14                        |

| Mode             | CI                                        | Legacy SSM                                           | ArgoCD delivery                         |
| ---------------- | ----------------------------------------- | ---------------------------------------------------- | --------------------------------------- |
| paused (default) | Chạy                                      | Bỏ qua                                               | Chưa có                                 |
| ssm              | Chạy                                      | Cho phép main push/dispatch sau environment approval | Chưa có                                 |
| argocd           | Chạy                                      | Bỏ qua                                               | Reserved, chưa triển khai trước CP15/16 |
| invalid          | Checks độc lập vẫn chạy; mode policy fail | Bị chặn                                              | Bị chặn                                 |

Đặt `argocd` ở CP02 không triển khai workload. Chế độ này chỉ được nhận diện để bảo đảm không rơi về SSM. Giữ OIDC immutable subject/environment `aws-demo`, không sửa IAM/SSM document hoặc quyền AWS.

Bootstrap vẫn là workflow manual riêng trong `aws-bootstrap` có reviewer riêng; không chạy bootstrap trong CP02. Không coi paused là cơ chế chặn mọi thao tác operator, hay dừng mọi tiến trình trên EC2.

## Kiểm chứng

- Tests chạy script mode thật: default/missing, ba modes, invalid/output injection, pre-credential guard chỉ cho phép ssm.
- Tests đọc điều kiện `if` thật từ hai workflow và kiểm tra matrix push/PR/dispatch × main/checkpoint × paused/argocd/ssm/invalid/empty. Không gọi AWS hoặc tự đẩy vào main chỉ để kiểm thử guard.
- Tests xác nhận checks không phụ thuộc deploy/publication, reusable/manual không bỏ qua policy, guard đứng trước credentials và concurrency không bị đổi.
- Cả bootstrap/deploy giữ group `lynk-aws-deployment`, `cancel-in-progress=false`; lock node và migration Jobs giữ nguyên.
- HTTPS `/health/ready` sau freeze trả 200 với database ok, TLS verify=0. Không chạy public smoke tạo dữ liệu.

Node verification SSM command `534dfd18-22e5-47b4-9250-ad311f07b4ff` Success/exit 0: shared deployment lock lấy được (idle); Kafka topics Job active=0/succeeded=1; Lynk vẫn deployed revision 6 với commit `b6cc75a477df508eadda3b0f57d9a9994b304a11`. Stdout metadata nằm trong evidence, không có secret values.

Kết quả local: lint và full repository format check pass; actionlint pass; Ansible syntax, cfn-lint, Helm lint và shell syntax pass. Mode tests 4/4, workflow gate tests 4/4 (matrix 60 trường hợp), deployment failure tests 7/7 pass; hai Application source contracts pass. Không gọi cluster apply trong các checks này.

`RUN_INTEGRATION_TESTS=true npm run test` lần đầu **exit 1**: auth và redirect integration `beforeAll` timeout 60 giây; các integration cases tương ứng chưa chạy. URL 16/16 và shared 4/4 pass trong lần đó. Chạy lại riêng từng workspace lỗi với `--maxWorkers=1 --no-file-parallelism`: auth 5/5 và redirect 17/17 pass, không skipped; tổng 42 test cases đã pass qua các lần chạy. Không đổi timeout, assertions hoặc source ứng dụng. Không ghi rằng lần chạy full-suite đầu đã pass. CI branch sẽ chạy lại full suite theo cấu hình chuẩn.

Pre-flight mã ứng dụng: không đổi architecture hoặc business API; kiểm tra local imports đều `.js`, services không có Fastify request/reply hoặc `console.log`, ba Dockerfiles có `USER node`. Bằng chứng chỉ chứa metadata và được review/scan để tránh PostgreSQL URI, access keys, private-key/token values.

CI push branch là kiểm chứng live cho đường kiểm tra không PR. Trường hợp push main/PR được kiểm tra bằng điều kiện workflow thật ở local/CI, không chạy một release production để chứng minh pause. Main cũ được bảo vệ bằng environment gate đọc lại qua API. Không suy ra rollout success từ CI success.

## Quay lại có kiểm soát

Revert commit CP02 chỉ phục hồi source; không tự phục hồi GitHub environment/variable. Live settings phải quay lại riêng, sau khi kiểm tra không có deployment/migration đang chạy và xác định rõ release muốn deploy.

Muốn dùng legacy SSM với source mới: đặt repository `LYNK_DEPLOY_MODE=ssm`, giữ reviewer gate, chọn SHA đã kiểm chứng và phê duyệt job cụ thể. Không cần bỏ protection để chạy SSM.

Nếu thực sự cần trở lại cấu hình gate trước CP02, metadata trước đã lưu trong evidence. Payload khôi phục (operator review trước khi dùng):

```json
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": [],
  "can_admins_bypass": true,
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
```

Gửi payload qua `gh api --method PUT repos/ngqkhai/lynk-url-shortener/environments/aws-demo --input <file>`. Branch policy main giữ nguyên. Xóa repository variable bằng `gh variable delete LYNK_DEPLOY_MODE` chỉ phục hồi trạng thái metadata trước; source mới vẫn default paused. Source cũ trên main không đọc biến, nên gỡ reviewer gate có thể cho delivery cũ chạy lại. Các lệnh phục hồi này **chưa chạy** ở CP02.

## Bài học và bàn giao

Pause **delivery** nghĩa là không đưa release mới vào runtime. Nó không scale Pods về 0 và không làm ứng dụng ngừng phục vụ. Source code/job condition và GitHub environment là hai lớp kiểm soát riêng, cần đường rollback riêng.

Actions concurrency serialize runner jobs; node lock serialize entrypoint trên EC2. Runner gửi một SSM command rồi theo dõi tiến trình bên ngoài: mất runner hoặc hủy polling không bảo đảm SSM/migration đã dừng. Không cancel giữa migration để “freeze”.

Bài tập: giải thích vì sao tắt runner chưa chắc dừng migration trên EC2. Câu hỏi kiểm tra: khi source CP02 chưa vào main, lớp nào đang chặn main legacy CD; lớp nào giữ CI hoạt động?
