# AWS deployment execution log

## Configuration

- AWS profile: `ngqkhai-dev`; region: `ap-southeast-1`. STS identity verified 2026-10-09 using local SSO credentials.
- Compute: one `t3.small` (2 vCPU / 2 GiB), gp3 30 GiB, CPU credits Standard. Treat capacity as an experiment until rollout/recovery/load gates pass.
- Kubernetes: single-node K3s, Helm-managed Traefik and Lynk; managed PostgreSQL on Neon Free.
- Neon project: `restless-water-85518233`; branch `production`.
- Domain: `lynk.codes`; authoritative DNS at Name.com.
- Full Sprint 3A: auth, ownership, phantom mTLS, outbox, Kafka/Redis.

## Automation ownership

- Terraform: VPC/subnet/Internet Gateway/routes, Security Group, instance/IAM role, EBS, Elastic IP. Record resource IDs for import; never commit state or credentials.
- Ansible: OS packages/sysctl, version-pinned K3s/Helm, node configuration, secret provisioning and Helm bootstrap.
- Helm: deployments, probes, migration Jobs, Middleware/Ingress and Kafka/Redis.

## Execution checkpoints

1. AWS SSO identity check succeeded. Existing `default` profile must not be used; explicitly select `ngqkhai-dev`.
2. Neon CLI authentication/setup in progress. Never print connection strings/passwords/API tokens in logs.
3. Infrastructure and deployment resources will be appended with commands, verification, costs and rollback as each step completes.

## Cost guardrails

Estimated 730-hour baseline: t3.small $19.27 + 30 GiB gp3 $2.88 + one IPv4 $3.65 = $25.80/month, before AWS credits, traffic/snapshot costs and tax. Neon bills separately. Free account expiration and credit remaining must be checked in Billing. No automatic account upgrade or instance resize.

## Rollback and teardown

Keep Neon data and persistent Kafka volume when replacing application Pods. Capture snapshots/backups before deleting disks. Teardown applies only to resources tagged for this deployment. Record the exact resource inventory before provisioning.

## Provisioned resources

CloudFormation stack `lynk-k3s-dev` owns the AWS resources. Import into Terraform only after ownership transfer; do not let both reconcile the same resources.

- ArtifactBucket: `lynk-k3s-dev-artifactbucket-acumvnfx55sd`
- VpcId: `vpc-09c4afddd4dfc6502`
- InstanceId: `i-03bb7dcb94ec8bd21`
- PublicIp: `3.1.88.80`
- SecurityGroupId: `sg-0548386ccc4cb294f`
- SubnetId: `subnet-00400b58035a53c92`

- Ubuntu 24.04 AMI: `ami-09fad7bb72d4e6685`.
- K3s: `v1.37.1+k3s1`; Helm: `v3.21.2`; Traefik chart: `41.5.0`.
- K3s disables bundled Traefik/ServiceLB; public ingress uses host ports.
- AWS Secrets and access: temporary SSH key manually approved, carried only over SSM tunnel; port 22/6443 not open to Internet. Credential transfer uses encrypted SSH stdin, not SSM command parameters/S3.
- PostgreSQL 18 preview migrations passed for all three services on `aws-migration-check`.
- Neon CLI 8.1.0 installed; project-scoped MCP and Codex skills installed. `neon.ts` config plan/deploy produced no remote changes.
- AWS account plan API returned ResourceNotFound; verify actual credit balance/account expiry in Billing. SSO identity does not prove credits are active.

## Neon Free behavior

AWS values configure outbox idle reconciliation every 30 minutes, waking immediately after committed URL creation. Pending/leased/backoff events stay on 1-second retry; startup reconciles existing backlog. Crash before notify remains durable and is recovered at startup or reconciliation. Default local/staging interval stays 1 second.

Dependency readiness results may be cached for 15 minutes to avoid constant SQL wakeups; this cache does not apply to authorization or business queries. Failed dependency probes are not cached as healthy. Business-query failures can invalidate the cache in URL/redirect error handlers. Account quota and cold-start latency must be monitored; autosuspend is not a guarantee of staying in the Free quota under real traffic.

## Deployment troubleshooting

- PostgreSQL 18 requires the admin to be able to SET ROLE before creating a database with that owner. Grant membership from app role to admin (not vice versa), then use SET ROLE for ownership-only grants; app users remain ordinary restricted roles.
- Save generated credentials before CREATE ROLE/DB so a partially failed provision can be resumed.
- Secrets transfer permission fix: wildcard expansion must run as root (`sudo find ... -exec chmod`) because the secrets directory is mode 0700.
- Traefik chart 41.5.0 rejects ACME with a DaemonSet. AWS uses a Deployment with one replica and maxSurge=0/maxUnavailable=1; local kind DaemonSet stays unchanged.
- Docker image import through SSM took ~124 seconds for a 78 MiB archive. Containerd image IDs were verified after import. Private S3 artifact bucket with 7-day expiry is available for subsequent faster artifact downloads.

2026-10-09: user confirmed $100 AWS credit is available in account `231136241975`. DNS A `lynk.codes` verified as `3.1.88.80`; no AAAA record. Three production migration Jobs and Kafka topics Job completed successfully.

## t3.small bootstrap CPU pressure

CloudWatch CPUCreditBalance dropped from 3.255 at 17:35 UTC to 0 at 17:45 UTC during provisioning/rollout. Kernel logs showed CPU workqueue stalls; K3s and several Pods restarted. Probe deadlines were too short during the startup burst. AWS temporarily enables Unlimited for at most 30 minutes with an automatic Standard reversion process; maximum theoretical surplus for two vCPUs over this window is $0.05. This does not change instance size or account plan. Runtime feasibility must be rechecked after returning to Standard.

AWS overlay increases liveness/readiness tolerance. Kafka readiness was first slowed to 60 seconds, then replaced with a TCP probe after Java CLI timeouts persisted; see the final probe correction below.

## Recovery evidence

After reboot, K3s returned Ready and all previous workloads recovered. At the recovery snapshot the node used 1361 MiB (71%), CPU180m (9%). Failed URL migration logs showed DNS EAI_AGAIN during the disrupted CoreDNS period. R2 migration CLI uses a15s connect deadline (previous2s), and the Helm hook is retried after DNS becomes ready. No kernel OOM line was observed in the filtered kernel logs; container Error137 alone must not be labeled OOMKilled.

## Public acceptance

2026-10-09: HTTPS certificate validation and `/health/ready`200 verified. AWS full3A smoke passed: register/login opaque tokens, mTLS phantom, owner A/B metadata isolation, refresh reuse revocation, logout, public302 and read model replication beforefirst click. CPU mode returnedStandard (verifiedAPI). Node feasibility is assessed with low-loadbenchmark/rollout checks, not inferred fromspecs.

## Standard-mode measured acceptance and limitation

Full HTTPS 3A smoke passed. A60s k6 run requested2owner metadata/s and10redirect/s:120metadata checks +594redirect checks passed,0failed HTTPrequests,8droppediterations. CombinedHTTP latency median40.96ms,p95471.28ms,p991051.86ms,max1761.64ms. These aggregate values mix both paths and setup/teardown; they are not a redirect-only latency claim. Artifact: docs/experiments/results/aws/k6-summary.json (no setup_data/tokens).

A Standard-mode snapshot showed1472MiB77% nodeworking-setmemory and440m22%CPU. Earlier idle snapshot1361MiB71%memory,180m9%CPU. These are point-in-time snapshots, not guaranteed capacity.

K3s journal revealed fatal at18:25:27UTC: `Transaction commit failed: sql: transaction has already been committed or rolled back`, followed by systemd auto restart. This is datastore/control-plane failure, not an observed kernelOOM. Publiccontainers survived the control-plane outage. Treat this t3.small deployment as a portfolio experiment; do not claim production stability.

HTTPredirect internal-port correction: entrypoint namewebsecure resolves container8443, so use explicitpublictarget `:443` with hostPort443.

Kafka recovery probe initially timed out at180s even though broker/group were serving. Readiness CLI bootstraps localhost then follows advertised `kafka:9092`, creating a self-service hop. AWS advertises stable brokerPod DNS `kafka-0.kafka-headless:9092` to remove readiness/self-service dependency, keeping the bootstrapService for clients and preservingPVC/clusterID. This is verified with another recovery test; the initial timeout is recorded as a failed gate, not hidden.

Kafka probe correction: Java CLI readiness still exceeded20s on t3.small Standard even with a live broker and group joins. AWS now uses a low-cost TCP readiness probe; this detects listener availability, not topic/leader health. ProvisioningJob and acceptance tests verify topic creation, produce/consume, outboxdrain and lag separately. Local kind retains its CLI probe. This avoids repeated JVM startups and leaves more CPU for K3s/datastore work.

NeonFree final cost tuning: readiness cache windows align to common15-minute wall-clock boundaries; outbox idle reconciliation aligns to30-minute boundaries. This avoids staggeredPod startup causing overlapping5-minute warm windows. Failedprobes are not cached and auth is alwaysintrospected. Compute capped0.25CU for low-loaddemo, autosuspend0meansplan-default300s. With alignedidlequeries, theoreticalbase compute~60.8CUh/month beforetraffic,cleanup/coldstart/extraoperations; actualquota muststill be monitored.

AWS Standard broker outage/recovery/outboxdrain + no-surge URLrollout acceptancepassed afterTCPprobe correction. Replica count restored1.

## Final handoff — 2026-10-09

- Final application images: `aws-20261009-r3`; Lynk Helm revision 5. Images are imported into containerd with `pullPolicy: Never`; automated registry publication and AWS rollout are future work.
- Final SSM snapshot: auth, URL, redirect, Kafka and Redis all `1/1 Running`. Redirect had one startup restart; Redis had one restart from the earlier host reboot. All three migration Jobs completed; the URL Job retried one failed Pod successfully.
- Public HTTPS `/health/ready` returned 200 with database `ok` and certificate verification enabled. Full public 3A smoke and broker recovery/outbox drain acceptance passed on R2; R3 timing changes passed the 42-test suite and final readiness check.
- Build, lint and all 42 tests passed. Production dependency audit has zero findings; development dependencies still have 7 findings (5 moderate, 2 critical), requiring a separate tooling upgrade.
- EC2 is back in Standard credit mode. K3s `NRestarts=1` at final check; the earlier SQLite/Kine fatal error remains a stability limitation, not a resolved production guarantee.
- Temporary SSH key was removed from `authorized_keys` and its local copy deleted; the SSM tunnel was terminated. Local temporary provisioning keys and database credential JSON were removed. Persistent database connection settings are in gitignored `.env.aws.local` (0600); runtime secrets remain in `/opt/lynk/secrets` (root only). Future certificate rotation needs secure recovery or regeneration of the signing keys; temporary local signing keys are not retained.
- Resource IDs and bootstrap steps above are recorded for Terraform/Ansible migration. CloudFormation currently owns AWS infrastructure; Terraform/Ansible modules have not been implemented. No commit or push was made.
