# AWS CI/CD and bootstrap

Current handoff: [CP17 acceptance](deployment-checkpoints/cp17-release-evidence-and-capacity.md) and [CP18 operating lesson](deployment-checkpoints/cp18-operating-evidence.md). The accepted release is source `9673a0e`, run [38981715213](https://github.com/ngqkhai/lynk-url-shortener/actions/runs/38981715213), GitOps revision `032e64a`. This is a dated acceptance, not a live health guarantee. Read current heads, deployment mode and runtime before acting.

## Ownership and access

| Component                                                                                | Current writer                             | Boundary                                                                                                    |
| ---------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| AWS EC2/network/EIP/EBS, IAM/OIDC, SSM documents and S3 policies                         | Terraform `infra/terraform/`               | Remote versioned state/locking; both legacy CloudFormation stacks retired with Retain. Never recreate them. |
| Host packages, pinned tools, Vault files, backup timers, Argo installation/status helper | Ansible `infra/ansible/`                   | SSM transport; default host bootstrap does not reconcile application workloads.                             |
| Three application Deployments, Services/routes, migration and smoke hooks                | Argo Application `aws-demo`                | Annotation tracking, selfHeal true, prune false; Helm is the renderer.                                      |
| Traefik/Gateway CRDs, Kafka, Redis and persistent storage outside that Application       | Operator-managed existing platform         | Separate reviewed maintenance; do not assume Argo health covers them or enable prune/adoption implicitly.   |
| lynk_urls / lynk_redirects / lynk_auth                                                   | URL / redirect / auth service respectively | Own-role backups; no cross-service SQL access.                                                              |

`LYNK_DEPLOY_MODE=argocd` selects GitOps delivery. Environment `aws-demo` restricts deployment to main and requires reviewer `ngqkhai`; approval is per run. `AWS_STATUS_ROLE_ARN` is the dedicated OIDC role restricted to the `LynkArgoStatus` document and one instance. The legacy `lynk-github-deploy` inline policy is now explicit Deny; old `Deploy AWS`/`LynkDeploy` delivery is retired. Do not switch to `ssm` as a recovery shortcut.

Environment `aws-bootstrap` has a distinct privileged role and Vault password secret; default check mode and reviewer gate remain. GitHub bootstrap OIDC has not been proven end-to-end by CP17; local SSO bootstrap is separate evidence. Argo access is private through SSM and the node's loopback `127.0.0.1:8443` port-forward service. Do not expose Argo, SSH or Kubernetes API publicly or export credentials into Git.

## Application delivery

1. CI validates source, automation, Terraform and GitOps. Image classifier considers the three service trees, shared package, root package/tsconfig inputs, `.dockerignore` and `.github/workflows/ci.yml`. An unavailable base fails safe by requesting a build. GitOps/docs/infra-only changes with known base skip images.
2. Main image-input changes publish three SHA-tagged images at `ghcr.io/ngqkhai/lynk-{url,redirect,auth}-service`, record immutable digests and package a checksum-verified release. Anonymous pull is an explicit gate; it passed for the accepted release.
3. The promotion job waits for the `aws-demo` reviewer and serializes with `lynk-argocd-promotion` concurrency, without cancellation. It checks fresh source against main, validates chart ancestry and changes only `infra/k8s/helm/lynk-services/values-aws-demo.yaml` on the dedicated `aws-demo` branch using GITHUB_TOKEN. Stale sources and competing pushes fail; no force push. A no-op preserves the existing revision.
4. Argo watches `aws-demo`, renders the pinned chart lineage (`87eb226`) and runs PreSync migration Jobs, app reconciliation and PostSync smoke. Names, PVC and certificate storage stay intact. A chart change on main requires separate reviewed chart promotion; the one-file release path cannot deliver it.
5. GitHub assumes the read-only status role. The fixed host checker waits for exact values revision, successful operation, Synced/Healthy, observed Deployment generations, ready Pods with expected imageIDs and source SHA startup logs, plus successful smoke evidence. It uses one 840s deadline; each kubectl call is bounded. SSM execution timeout 900s and caller bound 930s do not themselves implement convergence polling.
6. Record source SHA, manifest/digests, GitOps revision, Argo operation, Pod identities and smoke separately. CP17 also ran full public auth/ownership/refresh/logout/redirect/replication smoke with failure injection disabled. That synthetic test creates accounts/URLs; it is not a load benchmark.

A green quality job or a local runner commit does not establish deployment. Docs-only main commits can advance while source `9673a0e` remains the live release. Read [CP17 evidence](deployment-checkpoints/evidence/cp17-release.json) and live state before drawing conclusions.

## Failure and recovery

Start with the failed layer: CI/build → artifact/checksum → reviewer/promotion → Argo operation/hooks → Pod readiness/provenance → public request. Inspect remote aws-demo head before assuming a push occurred. Rerunning an old workflow retains its old source SHA/ref and does not pick up fixes on main.

If status fails after a new promotion, the workflow attempts to revert that promotion only when deployment head still equals its promotion and main still equals its source. Otherwise it refuses and requires operator reconciliation. Revert restores desired values; the workflow stays failed, and successful recovery still requires checking Argo revision, Pods and smoke. A returned git push alone does not prove recovery.

For manual recovery, first record current heads, operation and intended known-good values. Review an allowlisted values change against current aws-demo, keep concurrent delivery serialized and use a normal push. Do not use Helm rollback on the adopted app, force push, cancel an active migration or blindly retry a stale source. If current source freshness makes automation refuse, reconcile the new source/desired state explicitly.

Application rollback restores images/manifests; it does not undo database schema, restore deleted rows, recover private signing keys or restore EBS. Migrations must remain expand/contract compatible. Use [CP11 backup/restore](deployment-checkpoints/cp11-db-backup-restore.md) for data and [CP10 PKI](deployment-checkpoints/cp10-mtls-rotation.md) for certificates after reviewing their maintenance boundaries. Production fault injection/restore was not used to prove CP17 rollback; local race/timeout/revert fixtures cover that logic.

## Bootstrap and version limits

Use `Bootstrap AWS host` from main, inspect its default check-mode result, and pass the separate aws-bootstrap reviewer gate before an intended apply. It initializes the pinned backend read-only, derives one host from allowlisted Terraform outputs and restores encrypted recovery material into a private controller directory. Passwords stay out of argv. Existing secret bytes must match Vault; bootstrap does not regenerate keys silently.

Pins: Terraform `1.16.6`, AWS provider `6.69.1`, Ansible core `2.19.3`, K3s `v1.37.1+k3s1`, Helm `v3.21.2`, AWS CLI `2.31.18`, Argo CD `v3.5.5`; current Traefik chart `41.5.0` / image `v3.7.13`. Read source pins and live versions rather than silently upgrading. Node is one t3.medium, Standard credits, 30 GiB gp3. No automatic larger instance, Unlimited or HA. CP17 usage snapshots and successful rollout do not establish a production SLO.

## Backups and diagnostics

Three separate own-role timers use UTC 02:00 URL, 02:15 redirect, 02:30 auth. Private bucket uses SSE-S3 AES256, retaining at most seven successful backups per database and pruning after success. At CP18 snapshot, all timers were active but LastTrigger was empty; first automatic firing remains unobserved. Prior manual backup/local restore evidence is not proof of future daily operation. Inspect LastTrigger, service exit timestamp, journal and new manifest/checksum together.

Read-only release tracing commands and exercises are in [CP18](deployment-checkpoints/cp18-operating-evidence.md). Collect filtered metadata; never publish raw Terraform state, Vault files, tokens or connection strings. CP17 records an unresolved principal-simulator Organizations denial inconsistent with the management-account context/live status execution. Custom simulation checked the identity-policy layer only. This limitation is retained; no permissions were broadened to make a simulator pass.

Historical direct SSM/Helm and initial GHCR visibility failures remain in checkpoint evidence and the [deployment execution history](aws-deployment.md). They are not the current operating procedure.
