# AWS DevOps Assignment 3 — Kubernetes Deployment

The same 3-service application from Assignments 1–2 (nginx frontend, Flask backend, Flask worker), now running as Pods in Kubernetes instead of directly on EC2. See `diagrams/architecture-diagram.svg` for the full visual diagram and `screenshots/` for evidence the deployment works end to end.

## Cluster Choice

This deploys to a **local k3d cluster** (k3s in Docker), not AWS EKS. This is a deliberate, documented choice: EKS has an hourly control-plane cost on top of node costs, and for a course project focused on demonstrating Kubernetes concepts (Deployments, Services, ConfigMaps, Secrets, Ingress, probes, RBAC, NetworkPolicy), a local cluster exercises the exact same Kubernetes API and manifests with zero additional cost. Everything here is portable to EKS — the manifests use no k3d-specific APIs — the only cluster-specific detail is the Ingress class (`traefik`, which k3d ships by default; EKS would typically use `alb` or a Nginx Ingress Controller instead).

## Database Choice

Postgres runs **inside the cluster** (`k8s/03-postgres-deployment.yaml`), not against the real RDS instance from Assignments 1–2. This is also deliberate: the real RDS instance (`aws-devops-db...rds.amazonaws.com`) is intentionally not publicly accessible (`Publicly accessible: No`), which is correct security posture — but it means a Kubernetes cluster running on a laptop, outside the VPC, has no private network path to it without VPN/peering infrastructure that's out of scope here. The alternative — making RDS public just so a local cluster could reach it — would have been a worse security tradeoff than the one we're already taking.

This has real, documented consequences, which we deliberately did not paper over:
- **No managed backups.** RDS gives point-in-time recovery; this Postgres pod has none.
- **No Multi-AZ / high availability.** A single pod, single point of failure.
- **Ephemeral storage.** No PersistentVolumeClaim is attached, so Postgres's data lives only in the pod's container filesystem. We hit this directly during development: after a cluster restart, the `records` table and all prior rows were gone, because the Postgres pod restarted with a clean filesystem. This is expected behavior given the setup, not a bug — see `screenshots/` for the before/after evidence. A production deployment would add a PVC backed by durable storage (or just use RDS directly, from a cluster actually running inside the VPC, e.g. on EKS).

S3 and SNS, in contrast, connect to the **real AWS resources** from Assignments 1–2 (bucket `aws-devops-uploads-3454b8b3`, SNS topic `aws-devops-notifications`) — those are reachable over the public internet by design (via authenticated API calls, not open access), so there was no reason to fake them locally.

## Architecture

Internet → Ingress (Traefik) → frontend Service → frontend Pod (nginx, unprivileged)
|
+------------------+------------------+
| |
backend Service worker Service
| |
backend Pod (Flask) worker Pod (Flask)
| |
postgres Service AWS S3 (real) + AWS SNS (real)
|
postgres Pod


Only the frontend is reachable externally, via a Kubernetes Ingress. backend, worker, and postgres are only reachable inside the cluster, and — since k3d's bundled NetworkPolicy controller actually enforces this (see Security section) — only from the specific pods that are supposed to reach them.

## Prerequisites

- Docker Desktop (WSL2 backend), running
- WSL2 with an Ubuntu distro
- `kubectl` (v1.36+) and `k3d` (v5.9+) installed inside WSL
- AWS CLI configured with a scoped IAM user (`k8s-worker-user`) that has `s3:PutObject`/`s3:AbortMultipartUpload` on the app bucket and `sns:Publish` on the app topic — nothing broader

## Repository Structure

Kubernetes/
├── k8s/
│ ├── 00-namespace.yaml
│ ├── 01-configmap.yaml
│ ├── 02-secret.example.yaml # committed placeholder — fill in and rename/copy locally
│ ├── 02-secret.yaml # real values — gitignored, never committed
│ ├── 03-postgres-deployment.yaml
│ ├── 04-postgres-service.yaml
│ ├── 05-backend-deployment.yaml
│ ├── 06-backend-service.yaml
│ ├── 07-worker-deployment.yaml
│ ├── 08-worker-service.yaml
│ ├── 09-frontend-deployment.yaml
│ ├── 10-frontend-service.yaml
│ ├── 11-ingress.yaml
│ ├── 12-serviceaccounts.yaml
│ └── 13-networkpolicy.yaml
├── docker/
│ ├── backend/ # Dockerfile + app.py + requirements.txt
│ └── worker/ # Dockerfile + worker.py + requirements.txt
│ # frontend uses the stock nginxinc/nginx-unprivileged:alpine image directly —
│ # no custom image needed, config is injected via ConfigMap
├── diagrams/
│ └── architecture-diagram.svg
├── screenshots/
└── README.md


## Deployment

```bash
# 1. Create the cluster (maps host port 8080 -> Ingress port 80)
k3d cluster create devops-k8s --port "8080:80@loadbalancer" --agents 1

# 2. Build and load the custom images (frontend uses a public image, no build needed)
docker build -t devops-backend:v1 ./docker/backend
docker build -t devops-worker:v1 ./docker/worker
k3d image import devops-backend:v1 devops-worker:v1 -c devops-k8s

# 3. Create your real Secret from the example (fill in actual values, do not commit)
cp k8s/02-secret.example.yaml k8s/02-secret.yaml
# edit k8s/02-secret.yaml with a real DB password and the k8s-worker-user AWS credentials

# 4. Apply everything except the example secret
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl apply -f k8s/02-secret.yaml
kubectl apply -f k8s/03-postgres-deployment.yaml
kubectl apply -f k8s/04-postgres-service.yaml
kubectl apply -f k8s/05-backend-deployment.yaml
kubectl apply -f k8s/06-backend-service.yaml
kubectl apply -f k8s/07-worker-deployment.yaml
kubectl apply -f k8s/08-worker-service.yaml
kubectl apply -f k8s/09-frontend-deployment.yaml
kubectl apply -f k8s/10-frontend-service.yaml
kubectl apply -f k8s/11-ingress.yaml
kubectl apply -f k8s/12-serviceaccounts.yaml
kubectl apply -f k8s/13-networkpolicy.yaml
```

(Note: `kubectl apply -f k8s/` on the whole directory would also pick up `02-secret.example.yaml`, overwriting the real Secret with placeholder junk values, since it happens to sort after the real file alphabetically. Apply files individually as above, or move the example file outside `k8s/` if you want to safely bulk-apply.)

## Verification

```bash
kubectl get nodes
kubectl get pods -n devops-app
kubectl get deployments -n devops-app
kubectl get services -n devops-app
kubectl get ingress -n devops-app

curl http://localhost:8080/
curl http://localhost:8080/api/records
curl -X POST http://localhost:8080/api/records -H "Content-Type: application/json" -d '{"name":"test"}'
curl -X POST -F "file=@somefile.txt" http://localhost:8080/upload
```

Pod restart resilience:
```bash
kubectl delete pod -n devops-app -l app=backend
kubectl get pods -n devops-app -w   # Kubernetes recreates it automatically
```

All of the above were run and captured in `screenshots/` — see that folder for full evidence including the S3/SNS notification email.

## Security

**RBAC / ServiceAccounts.** Every workload (`backend`, `worker`, `frontend`, `postgres`) gets its own dedicated ServiceAccount (`k8s/12-serviceaccounts.yaml`) instead of sharing the namespace's `default` one. None of these workloads talk to the Kubernetes API — they only talk to each other, Postgres, and AWS — so no Roles or RoleBindings were created, and each ServiceAccount sets `automountServiceAccountToken: false` to remove the auto-mounted API token entirely. Minimizing what's granted, rather than granting broad access and hoping nothing misuses it, is itself the RBAC decision here.

**Secrets management.** `k8s/02-secret.example.yaml` is committed with placeholder values so the shape of the required secrets is documented; the real `k8s/02-secret.yaml` (actual DB password and AWS credentials) is gitignored and only ever applied locally. The AWS credentials themselves belong to a dedicated IAM user (`k8s-worker-user`) created specifically for this project, scoped to exactly `s3:PutObject`/`s3:AbortMultipartUpload` on the app bucket and `sns:Publish` on the app topic — not the personal admin AWS credentials. One honest limitation: Kubernetes Secrets are base64-encoded, not encrypted, by default — anyone with `kubectl get secret -o yaml` access to this cluster (or read access to etcd) can trivially decode them. Production Kubernetes should enable etcd encryption at rest and/or use an external secrets manager (AWS Secrets Manager, HashiCorp Vault) instead; out of scope for this local practice cluster.

**Network security.** `k8s/13-networkpolicy.yaml` implements default-deny-all ingress within the namespace, then explicitly allows only the intended paths: frontend accepts traffic from anywhere (it's the public entry point), backend and worker only accept traffic from frontend, and postgres only accepts traffic from backend — directly mirroring the security-group design from Assignments 1–2 (`rds-sg` only from `backend-sg`, `backend-sg`/`worker-sg` only from `frontend-sg`). This is actually enforced: k3d bundles a NetworkPolicy controller (based on kube-router's netpol implementation) alongside Flannel, and we verified it live — `nc` from the frontend pod to `backend-service:5000` (allowed) succeeded, while the identical test to `postgres-service:5432` (not allowed) was blocked (see `screenshots/11-networkpolicy-enforcement.png`). Egress is intentionally left open (same tradeoff as the EC2 security groups' default-allow egress) — restricting it would require explicitly allowlisting DNS, the Kubernetes API, and every AWS API endpoint each pod calls, which is reasonable production hardening but out of scope here.

**Container securityContext.** backend, worker, and frontend all run as a non-root user (`runAsNonRoot: true`, UID 1000), with `allowPrivilegeEscalation: false` and all Linux capabilities dropped (`capabilities: drop: ["ALL"]`). frontend specifically uses the `nginxinc/nginx-unprivileged` image rather than stock `nginx`, because stock nginx needs root to bind port 80 and write its cache directories — the unprivileged variant is built to run correctly as a non-root user on port 8080 instead. postgres is the one deliberate exception: the official Postgres image's entrypoint needs to start as root to fix data-directory ownership, then internally drops to the `postgres` user via a mechanism that itself requires `CAP_SETUID`/`CAP_SETGID` — forcing non-root or dropping all capabilities at the Kubernetes level would break that handoff and prevent Postgres from starting at all. So postgres only gets `allowPrivilegeEscalation: false`, and the rest of its privilege reduction is handled internally by the image itself. This is the same "explain any deviation from minimum" approach used for the EC2 security-group tradeoffs in the Assignment 1–2 README.

**Image security.** All images are pinned to specific versions (`postgres:16-alpine`, `python:3.11-slim`, `nginxinc/nginx-unprivileged:alpine`) rather than floating `:latest` tags, so deployments are reproducible and don't silently pick up breaking changes. Base images are minimal (`-slim`/`-alpine` variants) to reduce attack surface. `backend` and `worker` are custom-built from source and are not scanned by an automated vulnerability scanner (e.g., Trivy, Grype) in this project — that's a reasonable addition for a CI pipeline but out of scope for a manually-run local project.

**Ingress security.** The Ingress (`k8s/11-ingress.yaml`) routes only to `frontend-service` — backend and worker have no Ingress rules at all and are unreachable from outside the cluster, matching the requirement that only the frontend is externally exposed. Traffic is plain HTTP, not HTTPS/TLS — acceptable for local development against `localhost`, but a real deployment would terminate TLS at the Ingress (cert-manager + Let's Encrypt, or an AWS ACM certificate on an ALB Ingress in the EKS case) and redirect HTTP to HTTPS.

## Work Split

Solo project — all Terraform/Ansible (Assignments 1–2), Kubernetes manifests, image builds, and this documentation were completed individually.

## Repository

https://github.com/BarBalilos/<new-repo-name> (Kubernetes deployment for the AWS DevOps course project; Terraform/Ansible for Assignments 1–2 live separately at https://github.com/BarBalilos/AWS-DevOps-IaC)