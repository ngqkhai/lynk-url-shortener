# CP03 — Nguồn phục hồi secrets bằng Ansible Vault

CP03 lưu bộ runtime secrets hiện có vào Ansible Vault, không đổi credentials, JWT keys, mTLS hoặc workload. Branch `checkpoint/cp03-vault-recovery`; một commit, không tạo PR/merge. Chỉ sang CP04 khi người học nói “tiếp”.

## Mục tiêu và trạng thái đã thay đổi

Trước CP03, source runtime ở `/opt/lynk/secrets` trên EC2; bộ keys/credentials chưa có nguồn phục hồi mã hóa trong Git. Sau CP03:

- Ciphertext tại `infra/ansible/vault/aws-demo.tar.gz.vault` chứa đủ 11 file đang dùng.
- Mật khẩu random 48 bytes được mã hóa thành chuỗi URL-safe và lưu ngoài Git ở `.recovery/aws-demo.vault-password` (directory 0700/file 0600). File này là bản riêng trên máy operator, khác EC2; operator cần giữ thêm bản trong password manager hoặc thiết bị offline.
- GitHub environment `aws-bootstrap` có secret `ANSIBLE_VAULT_PASSWORD`; chưa có secret này trước CP03. Password được gửi qua stdin, không qua arguments, workflow inputs hoặc logs.
- Bootstrap source thêm bước verify Vault tại local runner bằng environment secret. Nó chưa nằm trên main và chưa chạy trên AWS qua Actions. Không đổi bước cung cấp runtime files hiện có; tích hợp bootstrap từ nguồn Vault trong CP09.
- CI kiểm tra framing ciphertext không cần production password, rồi chạy recovery tests bằng dữ liệu giả.

Không commit password, archive plaintext, transfer private key hoặc decrypted files. [.gitignore](../../../.gitignore) loại `.recovery/` và Python bytecode caches. Dữ liệu trong Vault là secrets/config; nó không chứa database rows và không thay thế DB backup ở CP11.

## Danh mục và giới hạn phục hồi

| File                   | Nội dung cần giữ                                | Kubernetes reference                         |
| ---------------------- | ----------------------------------------------- | -------------------------------------------- |
| auth.env               | DATABASE_URL của lynk_auth / role auth          | auth-service-db / DATABASE_URL               |
| url.env                | DATABASE_URL của lynk_urls / role URL           | url-service-db / DATABASE_URL                |
| redirect.env           | DATABASE_URL của lynk_redirects / role redirect | redirect-service-db / DATABASE_URL           |
| redis-password         | Redis authentication                            | lynk-redis-auth / redis-password             |
| jwt-private.pem        | JWT signing key                                 | lynk-jwt-keys / jwt-private.pem              |
| jwt-public.pem         | JWT verification key                            | lynk-jwt-keys / jwt-public.pem               |
| ca.crt                 | CA certificate để xác minh mTLS                 | lynk-gateway-ca / ca.crt                     |
| server.crt, server.key | Auth gateway identity                           | lynk-gateway-server / server.crt, server.key |
| client.crt, client.key | Traefik client identity                         | lynk-gateway-client / tls.crt, tls.key       |

DB credentials được giữ riêng cho từng service; CP03 không đăng nhập hoặc truy vấn DB. Không ghi connection strings, passwords hoặc private keys vào bảng này.

CA signing key cũ đã bị xóa theo runbook trước; collector xác nhận `/opt/lynk/secrets/ca.key` không tồn tại. Không coi kiểm tra đường dẫn đó là audit toàn bộ filesystem. `ca.crt` đủ để kiểm tra certificate được CA ký, nhưng không thể cấp certificate mới. CP03 bảo quản bộ đang chạy; CP10 mới thiết lập signing key có thể phục hồi và rotate mTLS.

## Cách thu thập và bảo vệ dữ liệu khi sử dụng

1. Tạo recipient RSA tạm ở directory local 0700; chỉ public certificate được đưa vào SSM command.
2. Collector chạy root, xác nhận directory secrets thuộc root/mode 0700, file thường/mode 0600, và đối chiếu bytes với tám Kubernetes Secrets tham chiếu trong bộ runtime.
3. Archive 11 file trong memory, mã hóa CMS AES-256-CBC với recipient RSA-OAEP bằng OpenSSL. SSM stdout chỉ nhận ciphertext và metadata an toàn; không có plaintext secret values, hashes của password hoặc private key.
4. Local dùng recipient private key giải mã vào directory 0700, đóng gói lại bằng Ansible Vault 1.2/AES256 với vault ID `aws-demo`.
5. Giải mã Vault, so sánh archive và 11 files byte-identical, kiểm tra permissions, JWT/mTLS key pairs và chain; cleanup plaintext và recipient private key.

Collector lần đầu từ chối vì giả định file owner=root. Metadata thực tế: directory owner=root/0700, file owner UID 1000/0600; cả 11 files khớp Kubernetes. Collector được sửa để giữ ownership hiện có và kiểm soát quyền truy cập bằng directory root-owned 0700 + files thường 0600. Không chown/chmod file runtime hoặc thay values.

Tham khảo: [Ansible Vault chỉ bảo vệ dữ liệu khi lưu trữ](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html), [Vault hỗ trợ binary files](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html), [OpenSSL CMS và RSA-OAEP](https://docs.openssl.org/3.0/man1/openssl-cms/). CMS phục vụ bước thu thập qua transport AWS đã xác thực; artifact lâu dài là Ansible Vault, có kiểm tra integrity khi decrypt. Không xây cơ chế mật mã riêng.

## Kiểm chứng và cách sử dụng

[Bằng chứng metadata](evidence/cp03-vault.json) ghi capture command, runtime equality, permissions, artifact checksum và roundtrip; không ghi ciphertext response từ SSM hoặc secret values.

Kiểm tra ciphertext trong CI không cần key:

```bash
python3 scripts/secrets/vault-bundle.py check
```

Lệnh này chỉ kiểm tra envelope/framing; nó không chứng minh decrypt được hoặc nội dung là đúng. Để verify thực tế ở local:

```bash
python3 scripts/secrets/vault-bundle.py verify \
  --password-file .recovery/aws-demo.vault-password \
  --ansible-vault /tmp/lynk-cd-venv/bin/ansible-vault
```

`verify` decrypt/extract trong directory tạm 0700, files 0600 rồi cleanup. Không dùng `ansible-vault view` vào terminal/logs. Nếu ansible-vault đã được cài đúng phiên bản trên PATH, có thể bỏ tùy chọn executable.

Khi operator cần một directory để phục hồi, chọn đường dẫn mới, chưa tồn tại; parent phải tồn tại:

```bash
python3 scripts/secrets/vault-bundle.py restore \
  --password-file .recovery/aws-demo.vault-password \
  --ansible-vault /tmp/lynk-cd-venv/bin/ansible-vault \
  --output-dir /tmp/lynk-restored-runtime
```

Directory đó chứa plaintext và do operator cleanup sau khi dùng. Helper từ chối directory có sẵn, duplicate/path traversal/symlink members và bundle thiếu files. Không tự overwrite keys. Trong CP03 chưa dùng directory restore để apply vào EC2 hoặc Kubernetes. Bootstrap hiện có hỗ trợ `lynk_secrets_dir`; CP09 sẽ chuẩn hóa việc nối nguồn Vault vào luồng này.

Recovery tests dùng fixture giả: đủ files/permissions/bytes và cleanup; password sai; ciphertext bị sửa; archive thiếu file, duplicate, traversal, symlink; destination đã tồn tại; password file mode không an toàn; password từ env cho bootstrap. 7/7 tests pass. Application tests 42/42 pass với integration enabled; lint, actionlint và Ansible syntax pass. Format, staged-secret review và CI branch được kiểm tra trước bàn giao.

CI run 38006065581 pass các checks Vault/application nhưng E2E fail ở polling ngay sau start read DB local: `psql` exit 2 (socket chưa sẵn sàng) làm predicate ném exception thay vì tiếp tục wait. Sửa riêng predicate `read_db_recovered` để exit 2 trả false và retry trong deadline 90 giây cũ; lỗi khác vẫn ném, assertion vẫn yêu cầu row đã được lưu. Không catch mọi lỗi hoặc bỏ test. Nhánh này chỉ chạy khi không AWS/KIND; không thay public API hay thực hiện fault injection production. [psql exit status](https://www.postgresql.org/docs/16/app-psql.html#APP-PSQL-EXIT-STATUS).

Bản password manager/offline do operator quản lý; chưa xác nhận đã sao chép. GitHub giữ bản dùng cho bootstrap, local file là bản operator nhận được. Không xem workspace file và GitHub secret là bằng chứng đã có password-manager/offline copy.

## Quay lại và vòng đời mật khẩu

Revert commit CP03 hoàn tác source/ciphertext ở branch, nhưng không xóa GitHub secret hoặc bản operator. Nếu thực sự trở lại cấu hình GitHub trước CP03, xóa **environment** secret bằng `gh secret delete ANSIBLE_VAULT_PASSWORD --env aws-bootstrap`; chưa chạy lệnh này. Giữ password và ciphertext nếu vẫn cần phục hồi; không xóa cả hai để “rollback”. Runtime không đổi nên không có rollout/database rollback ở CP03.

Không generate password mới khi bootstrap chạy lại. Rotation password Vault (`rekey`) khác rotation credentials/key ứng dụng: rekey thay lớp mã hóa, không tự đổi DB password/JWT/mTLS bên trong. Khi rekey về sau, phải đồng bộ ciphertext, environment secret và bản operator theo một quy trình riêng, kiểm chứng roundtrip rồi mới loại bản cũ.

## Bài học CP03

**Plaintext** là dữ liệu đọc được; **ciphertext** là dữ liệu đã mã hóa; **Vault password** cho phép mở ciphertext. File mã hóa có thể nằm trong Git, nhưng người có cả ciphertext và password sẽ đọc được secrets. Vì vậy password ở nơi khác, có quyền truy cập riêng.

**At rest** là dữ liệu đang được lưu (Git/ổ đĩa). **In transit** là lúc truyền giữa EC2 và operator. **In use** là lúc process đang đọc/decrypt/copy dữ liệu. Vault bảo vệ artifact at rest; collector mã hóa trước khi đi qua SSM logs; thư mục riêng, permissions, output suppression và cleanup bảo vệ bước sử dụng. Cleanup ở đây là xóa file/directory bằng hệ điều hành, không phải cam kết secure erase của SSD, snapshot hoặc RAM.

Permissions 0700 cho directory: chỉ owner được đọc danh sách/ghi/đi vào; 0600 cho file: chỉ owner được đọc/ghi. Quyền đi qua directory cha cũng quyết định truy cập, vì vậy file UID 1000 không đồng nghĩa user đó đọc được file bên trong directory root-only 0700.

Bài tập: theo đường Git ciphertext → password → decrypt → 11 files, chỉ ra bước nào còn cần bảo vệ plaintext. Câu hỏi kiểm tra: nếu mất password nhưng vẫn giữ ciphertext, có thể phục hồi JWT private key không? CA certificate trong Vault có đủ để cấp server certificate mới không?
