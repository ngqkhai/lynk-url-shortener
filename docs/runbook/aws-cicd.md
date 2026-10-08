# AWS CI/CD and bootstrap

## Ownership and prerequisites

CloudFormation stack `lynk-k3s-dev` retains ownership of the existing EC2/network/storage. Stack `lynk-cicd` owns GitHub OIDC roles, the `LynkDeploy` SSM document and the node artifact policy. No Terraform import occurs.

GitHub environments restrict deployment to `main`:

- `aws-demo`: `AWS_DEPLOY_ROLE_ARN`, `AWS_ARTIFACT_BUCKET`, `AWS_INSTANCE_ID` variables; no AWS access keys.
- `aws-bootstrap`: `AWS_BOOTSTRAP_ROLE_ARN`, manual reviewer `ngqkhai`; SSM session access permits root configuration and must remain separate from ordinary CD.

The pre-deploy CI gate explicitly checks anonymous image access. On initial inspection, URL latest returned 200; redirect/auth anonymous access returned 403 (private or not yet published).

Images must be **public** at `ghcr.io/ngqkhai/lynk-{url,redirect,auth}-service`. New GHCR packages default to private: set visibility to public in each package's settings before the first successful CD. Verify anonymous pull. `GITHUB_TOKEN` publishes inside Actions; no registry credential is stored on the node.

## Bootstrap

Use the manual `Bootstrap AWS platform` workflow from `main`. Its default is check mode; turn check off to apply and approve the `aws-bootstrap` environment. It uses `amazon.aws.aws_ssm` and S3 temporary transport, without SSH keys or public port 22/6443.

For local execution with the approved SSO profile:

```bash
python3 -m venv /tmp/lynk-ansible
/tmp/lynk-ansible/bin/pip install -r infra/ansible/requirements.txt
/tmp/lynk-ansible/bin/ansible-galaxy collection install -r infra/ansible/requirements.yml
AWS_PROFILE=ngqkhai-dev /tmp/lynk-ansible/bin/ansible-playbook -i infra/ansible/inventory.yml infra/ansible/bootstrap.yml --check
```

The Session Manager plugin must be installed on the controller. For fresh nodes, update inventory/resource parameters and provide an explicit secure local `lynk_secrets_dir`; otherwise missing secrets fail bootstrap. Existing secret files are never overwritten or regenerated. Do not pass passwords through workflow inputs. Recover or regenerate the signing CA separately before certificate rotation; the earlier temporary signing key was deleted.

Ansible pins OS tooling/K3s/Helm, installs the root-owned CD entrypoint, preserves runtime secrets and reconciles platform resources. Bootstrap is not part of every application deployment. Kubernetes version drift fails rather than silently upgrading. Core components run on one t3.small; capacity and SQLite/Kine stability remain limitations.

## Application delivery

1. PR: lint, format, build, full integration tests, deployment failure tests and gateway/Kafka E2E; no AWS deployment.
2. Push to `main`: publish three images with commit SHA tags, collect their immutable digests, package chart/AWS values/smoke/manifest into a secret-free release.
3. Reusable deploy workflow obtains OIDC credentials and uploads release/checksum to `releases/<sha>/` in the existing private artifact bucket. A different checksum cannot overwrite an existing release; rebuilds producing different digests require a new commit.
4. Invoke only `LynkDeploy` on the configured instance. Poll terminal status and retain full command output under `deploy-logs/` (14 days).
5. The node locks deployment, checks K3s/node/disk, downloads/checks archive, pre-pulls images sequentially, runs Helm migration hooks and upgrades digest-pinned Pods.
6. Public smoke verifies auth/opaque tokens/ownership/refresh reuse/logout/redirect and uses local kubectl for the redirect service's own DB replication check. Tokens stay in memory. Smoke creates synthetic accounts/URLs; data cleanup is a separate maintenance task.
7. Record successful commit/revision pairs in `/opt/lynk/releases/success.jsonl`.

Both workflows share concurrency; the node has a second lock. Existing deployments are never canceled automatically. Deploy OIDC credentials last 70 minutes (role ceiling two hours), covering the full 65-minute job without expiring during rollback. SSM has a 60-minute execution ceiling; the runner polls for 61 minutes inside a 65-minute job. The node lock waits at most two minutes and each artifact download has a two-minute bound, leaving time for image pull, upgrade and rollback. A runner polling timeout does not cancel a potentially active migration: inspect SSM before retrying. No instance resize or CPU credit mode change is automatic.

## Failure and rollback

Image/preflight failure occurs before Pod replacement. Helm upgrade or smoke failure attempts restoration of the previous Helm revision, checks smoke again, and always leaves the workflow failed. If restoration fails, inspect SSM logs and service status; do not report successful recovery.

Database migrations must use expand/contract and remain compatible with the previous app. Helm rollback restores workloads, **not** the database schema. Contract migrations require a separate reviewed rollout.

Manual `Deploy AWS` workflow supports redeploy of an already uploaded SHA, or rollback with a successful SHA/revision pair from `success.jsonl`. It can run only from `main`. The node verifies the pair before rollback. Helm retains 20 revisions. Releases are retained without the old seven-day expiry, including at least three successful releases; disk/registry cleanup is currently operator-managed and must preserve images for rollback. Initial imported R3 can be restored automatically by Helm before any CI release succeeds, but has no CI manifest for the manual SHA-based workflow.

## Validation

```bash
python3 scripts/cd/test-deploy.py
bash -n scripts/cd/deploy.sh scripts/bootstrap-aws-platform.sh
helm lint infra/k8s/helm/lynk-services -f infra/k8s/helm/lynk-services/values-aws.yaml
ansible-playbook -i infra/ansible/inventory.yml infra/ansible/bootstrap.yml --syntax-check
```

Failure scenarios cover image pull, migration, smoke/rollback, traversal rejection and successful release recording using simulated transports. The first main CI/OIDC delivery passed after the immutable-subject fix; see the recovery evidence below. Do not merge automatically merely to exercise CD.

## Execution evidence

- Initial Ansible apply succeeded on the existing instance; secrets and workload images were preserved. Repeat confirmed unchanged K3s configuration, tooling, runtime entrypoint and archive. Kafka's client-side apply reported configured despite a zero diff; reconciliation now checks diff before applying.
- Public application Pods remained Ready after bootstrap. Local validation: 42 app tests and seven deployment failure tests passed, as did lint/build/format, actionlint, cfn-lint, Helm lint and Ansible syntax.
- PR #1 includes the explicitly authorized previous Sprint 3A/AWS changes. Main's old GitOps image-tag commit conflicted; it was merged and the obsolete per-service tag removed. PR CI passed all three test groups before the final reconciliation adjustment.
- Initial production CD/OIDC acceptance was pending at this checkpoint; the first main delivery subsequently passed after the immutable-subject fix. The original delivery PR was merged by the user.

Transport acceptance on the live node: a deliberately incomplete release was downloaded and checksum-verified through `LynkDeploy`, then rejected before Helm; stdout/stderr reached private S3 (two output files). The test release was removed and the application remained on its existing Helm revision. This verifies the installed entrypoint and node/SSM/S3 path using SSO; This transport check alone did not prove GitHub OIDC; the later main workflow verified it. The Ansible collection calls S3 HeadBucket, so the bootstrap role additionally permits bucket listing/location lookup; object access stays limited to the instance transport prefix.

## OIDC subject mismatch recovery

Repository OIDC configuration returns `use_immutable_subject: true` and `sub_claim_prefix: repo:ngqkhai@92835482/lynk-url-shortener@1365808803`. Both role trust policies must append their environment to this exact prefix. The `GitHubSubjectPrefix` CloudFormation parameter keeps this explicit; inspect `gh api repos/ngqkhai/lynk-url-shortener/actions/oidc/customization/sub` when bootstrapping another repository. Do not infer subject format from repository name alone or widen the trust policy to a wildcard.

First main run `37839590947` passed CI, image publication and anonymous pulls but failed STS before any SSM deployment, because the original policies used the legacy subject. Update stack `lynk-cicd` with the immutable prefix, then rerun failed jobs (reuse the existing release artifact; do not rebuild the successful images merely to retry OIDC).

Recovery acceptance: main run `37839590947` succeeded on retry after the trust-policy update. OIDC authentication, S3 release upload, `LynkDeploy` execution, digest image pulls, migration hooks and Helm rollout all passed. Release `b6cc75a477df508eadda3b0f57d9a9994b304a11` is deployed as Helm revision 6. Public smoke passed opaque tokens, owner isolation, refresh reuse/logout, redirect and Kafka replication before the first click. PR #2 carries the CloudFormation/source fix; live AWS was updated without waiting for that PR to merge. These checks verify the delivery path, not high availability or a live rollback fault injection.
