# AWS setup (pilot: one app server + one sandbox server)

Step by step, from a new AWS account to a running staging environment.
`docs/DEPLOY.md` explains how the pieces work; this file is the checklist.

**What it creates** in `ap-south-1` (Mumbai), per environment:

| Piece | What | Rough cost/month |
|---|---|---|
| App server | EC2 `t3.xlarge` (production) / `t3.large` (staging), Elastic IP: Caddy (HTTPS), frontend, API, agent, worker, Redis | ~$120 / ~$60 |
| Sandbox server | EC2 `t3.small` with Docker + gVisor; only the app server can reach it (mutual TLS) | ~$15 |
| Database | RDS Postgres 16 `db.t4g.micro`, encrypted, 7-day backups + point-in-time restore | ~$15–20 |
| Buckets | recordings (private, encrypted, versioned) and ops (release bundles) | cents |
| Settings | SSM Parameter Store (encrypted) | free |

Shared once: image registry (ECR), Terraform state bucket, GitHub deploy role.
No NAT gateway or load balancer, which saves about $55/month. Costs are rough
estimates; check them in the AWS pricing calculator.

No SSH: shell access is through SSM Session Manager. GitHub holds no AWS keys
(it uses OIDC).

---

## 0. Before you start

- [ ] **Revoke the leaked Gemini key** (git history, commit `d77e1c8`) and make a new one.
- [ ] Separate API keys for staging (and later production): a new LiveKit Cloud
      project per environment, plus Deepgram, Cartesia, Beyond Presence and Gemini keys.
- [ ] A domain you control. Subdomains such as `staging.yourdomain.com` and `app.yourdomain.com` work.

## 1. AWS account (you, in the browser)

1. Create the account at aws.amazon.com and choose the **Paid plan**, so the
   credits apply and services don't stop when the free plan ends.
2. **Billing → Budgets → Create budget**: monthly cost budget of $50, with email alerts at 80% and 100%.
3. Turn on MFA for the root user. Then **IAM Identity Center** (or IAM) → create an admin
   user for yourself and stop using root.
4. Install the tools on your Mac:

   ```bash
   brew install awscli hashicorp/tap/terraform
   ```

5. Sign in from the terminal:

   ```bash
   aws configure sso
   ```

   (Or `aws configure` with an access key for your admin user.) Then check it works:

   ```bash
   aws sts get-caller-identity
   ```

## 2. Bootstrap (once per account)

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply
```

Save the outputs: `state_bucket`, `registry`, `deploy_role_arn`. This folder's
`terraform.tfstate` stays on your machine: back it up, for example in a password manager.
It holds no secrets.

## 3. GitHub repository

1. Push this repository to `ashish-066/letsee`. The deploy role trusts only that
   repository's `main` branch.
2. **Settings → Secrets and variables → Actions → Variables**: add `AWS_DEPLOY_ROLE_ARN` = the
   `deploy_role_arn` output.

## 4. Staging environment

```bash
cd infra/terraform/envs/staging
terraform init -backend-config="bucket=<state_bucket>"
cp terraform.tfvars.example terraform.tfvars    # set domain = "staging.yourdomain.com"
terraform plan -out plan.tfplan
terraform apply plan.tfplan
```

This takes about 10 minutes (the database is the slow part). Outputs: `app_public_ip`, instance IDs.

1. **DNS:** at your registrar, add an **A record** `staging.yourdomain.com` → `app_public_ip`.
2. **API keys:** put the staging keys in two files *outside the repo*, in the same
   `KEY=value` format as `avatar/.env` and `worker/.env`. Then upload them:

   ```bash
   scripts/aws/put-secrets.sh staging ~/alex-secrets/staging-avatar.env ~/alex-secrets/staging-worker.env
   ```

   Only the known API key names are uploaded, and values are never printed. The
   database, Redis, auth secret and S3 settings were already created by Terraform.

3. **Recordings (optional):** the bucket and its access keys exist, in SSM under
   `/alex/staging/avatar/S3_*`. Nothing else is needed.

## 5. First deploy

Push to `main` (or merge a PR). The **Deploy** workflow then:

1. builds the four images and pushes them to ECR, tagged with the commit SHA
2. uploads `deploy/` and runs `deploy/deploy.sh` on the app server through SSM. That script:
   - reads the settings from SSM
   - pulls the images and runs the migrations
   - starts the services
   - checks `/ready` and runs the sandbox self-check
   - starts the new agent and lets the old one drain
   - rolls back to the previous release if any check fails

Open `https://staging.yourdomain.com`. Caddy gets the TLS certificate on the first
request once DNS has propagated. Create the first account:

```bash
aws ssm start-session --target <app_instance_id>
```

Then, on the server:

```bash
sudo docker exec -it alex-api-1 python -m scripts.create_user --platform-admin
```

## 6. Production

Same as step 4, in `infra/terraform/envs/production`, with `app.yourdomain.com` and
the production keys (`put-secrets.sh production ...`). Production deploys only when
you start it by hand: **Actions → Deploy → Run workflow**, environment `production`,
tag = the commit SHA that is running fine on staging.

## Everyday operations

| Task | How |
|---|---|
| Deploy to production | Actions → Deploy → Run workflow → `production` + commit SHA |
| Roll back | The same, with an earlier SHA (the last 30 images are kept) |
| Change an API key | `put-secrets.sh <env> ...`, then redeploy the current SHA |
| Shell on a server | `aws ssm start-session --target <instance-id>` |
| Logs | On the app server: `sudo docker logs alex-api-1` (`alex-worker-1`, `alex-agent-<sha>-agent-1`, ...) |
| Database restore | RDS console → Restore to point in time (see docs/BACKUPS.md) |
| Stop staging overnight | Stop both EC2 instances and the RDS instance in the console. RDS restarts itself after 7 days. |

## What this pilot setup does not do yet

- **Single app server.** A deploy restarts the API and worker (about 10 s of errors). Live
  interviews continue on the old agent until they end. If the server dies, the site is down
  until it is replaced; data is safe in RDS and S3.
- Redis runs on the app server (AOF on its disk). Losing the server loses live call state,
  not interview results.
- Monitoring and alerting come in Phase 4.
- Scaling past one server means moving to EKS + ElastiCache (Stage B in the launch log).
