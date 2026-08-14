# Saved for later

This is a **design note**, not an active implementation track.
Revisit when the Ansible operator tax outweighs a 4–8 week platform-only Go rewrite.

---

# Assessment: Greenfield Go operator (no Ansible legacy)

## Question

How unreasonable is it to stop extending the Ansible-operator “soup” (`awx-platform-operator` soft-fork of `ansible/awx-operator`) and build a **new Go operator** without legacy?

## Short answer

| Scope | Unreasonableness | Verdict |
|-------|------------------|---------|
| **Replace full classic AWX installer** (backup/restore/mesh/route/postgres upgrade…) in Go | **High** — multi-person-year | Don’t |
| **New platform-only Go operator** for `AWXPlatform` + `AWXGateway` + thin Controller deploy | **Low–moderate** — weeks to a few months for a solid v1 | **Reasonable** |
| **Hybrid**: Go for platform/gateway; leave classic `AWX` on Ansible or don’t support it | **Low** | **Best path** if you want maintainability |

It is **not** unreasonable to write a Go operator **for the modern stack you actually care about**. It **is** unreasonable to re-implement the entire legacy AWX installer surface in Go just to escape Ansible.

---

## What you have today (quantified)

| Piece | Size / shape |
|-------|----------------|
| Runtime | Ansible Operator plugin; **0 Go reconcile code** |
| Watches | `AWX`, `AWXBackup`, `AWXRestore`, `AWXMeshIngress`, `AWXGateway`, `AWXPlatform` |
| `roles/installer` | ~62 files, ~456KB — the legacy weight |
| `roles/gateway` + `platform` | ~20 files, ~180KB — **your** product surface |
| CRD `AWX` | ~2100 lines, huge option surface |
| CRDs gateway/platform | ~150–200 lines each — small |

Pain you already hit is characteristic of ansible-operator:

- No `kubectl` in image → shell scripts break (`v0.1.4` JWT secret)
- Reconcile is playbook runs, not continuous status/conditions
- SSA/merge + “exists” jobs leave stale state (port 8052)
- Hard to unit-test; debug is operator log soup
- Soft-fork of upstream installer forever

Your **interesting** logic is almost all in **gateway + platform + trust**, not in the 10-year installer.

---

## Three options

### A. Keep Ansible, harden platform path only

- Continue `awx-platform-operator` as soft-fork  
- Fix issues as they appear (port, k8s_exec, cert-manager)  
- **Cost:** low short-term  
- **Risk:** same class of bugs forever; hard to hire/maintain  

### B. Greenfield Go operator — **platform-only** (recommended if rewriting)

**In scope for v1:**

| CR | Responsibility |
|----|----------------|
| `AWXPlatform` | Orchestrate children, trust, status |
| `AWXGateway` | Jewel, Redis (optional), Envoy, cert-manager TLS, register, JWT secret |
| `AWXController` *or* thin `AWX` subset | Deploy web/task/redis sidecars, Service, migrations Job, external Postgres only |

**Out of scope for v1:**

- Backup/Restore/MeshIngress  
- Managed Postgres StatefulSet + upgrade paths  
- Full classic `AWX` 2000-line CRD parity  
- OpenShift Route edge cases  

**Stack:** controller-runtime / kubebuilder (or operator-sdk Go), client-go, structured conditions, envtest.

**Rough effort (one strong engineer familiar with the stack):**

| Milestone | Time |
|-----------|------|
| Scaffold + CRDs + status types | 2–4 days |
| Gateway reconcile (Deployments/Services/Secrets/Certificates) | 1–2 weeks |
| Trust: register + JWT secret via client-go | 3–5 days |
| Controller thin deploy + migration Job + external PG | 1–2 weeks |
| Platform umbrella + e2e kind | 1 week |
| Helm chart + docs + cutover from ansible soft-fork | 3–5 days |

**Total v1:** ~**4–8 weeks** focused, not “years.”

**What you deliberately do *not* reimplement:** installer’s postgres upgrade, receptor CA gymnastics, every ingress variant, backup role, etc.

### C. Full Go rewrite of classic AWX operator

- Re-express ~installer templates + backup/restore + mesh as Go  
- Match community expectation for drop-in `kind: AWX`  
- **Cost:** large (many months); competes with Red Hat/community on a surface you don’t need for platform  
- **Verdict:** unreasonable for this project  

---

## Why Go is a good fit *for platform*

Your bugs map cleanly to Go strengths:

| Failure mode | Ansible | Go |
|--------------|---------|-----|
| Missing kubectl | Common | Use client-go only |
| Stale register port | Job + ensure() stringly | Reconcile loop always patches desired state |
| Secret not wired | One-shot order | Watch Secret; requeue AWX until present |
| TLS readiness | Wait loops in YAML | Condition `TLSReady` + requeue |
| Testability | Molecule/heavy | envtest + fake client |

API design can stay compatible with what GitOps already uses:

```yaml
apiVersion: awx.ansible.com/v1beta1   # or platform.awx.x-k8s.io/v1alpha1
kind: AWXPlatform
spec:
  postgres_configuration_secret: ...
  controller: { image, image_version, ... }
  gateway: { image, create_certificate, controller_service_port: "80", ... }
```

**API group choice:**

- Keep `awx.ansible.com` → easier GitOps migration, risk of confusion with upstream  
- New group `platform.awx...` → clean break, two operators can coexist during cutover  

---

## Hybrid cutover (lowest risk)

```text
Phase 0  Keep ansible soft-fork for production (0.1.x)
Phase 1  Go operator: AWXGateway only (side-by-side, different CR name or feature flag)
Phase 2  Go: trust + cert-manager + Envoy (replace gateway role)
Phase 3  Go: thin Controller + AWXPlatform umbrella
Phase 4  Stop reconciling platform CRs in ansible image; shrink or archive soft-fork
```

Classic `kind: AWX` users (if any) stay on ansible or on upstream; **you** only ship Go for platform installs.

---

## Controller: don’t boil the ocean

You do **not** need full installer parity. Platform controller needs roughly:

- Deployment web + task (+ redis sidecar if you want parity)  
- Service `80 → 8052` (or dual-publish)  
- Migration Job  
- Secrets: admin, secret-key, postgres config mount  
- Settings ConfigMap: `gateway_url`, JWT key, open_source_defaults  
- External Postgres only (you already decided that)

That is **dozens** of resource objects, not the whole installer role.

Optional later: controller internal HTTPS via cert-manager (as discussed) — independent of “Go vs Ansible.”

---

## When a Go rewrite is *unreasonable*

- Goal is “drop-in replace ansible/awx-operator for every existing AWX CR in the wild”  
- No bandwidth for a parallel codebase during cutover  
- Need Backup/Restore/Mesh on day one  

## When it is *reasonable* (your case)

- Product is **modern platform** (Jewel + Envoy + Controller + GitOps)  
- Soft-fork already diverged (gateway/platform/cert-manager/trust)  
- Pain is operational correctness and velocity, not missing Route/backup features  
- Team can own one Go controller-runtime binary  

---

## Recommendation

1. **Do not** rewrite full legacy installer in Go.  
2. **Do** treat a **platform-scoped Go operator** as a normal, justified project — not a moonshot.  
3. Prefer **new module/repo** e.g. `awx-platform-operator-go` (or rename later) with **narrow CRDs**, controller-runtime, kind e2e.  
4. Keep ansible soft-fork until Go gateway+platform is green on your `homeapps-test` cluster.  
5. GitOps stays Helm of the new operator; CR shapes can stay almost identical.

### Effort framing for decision-makers

| Approach | Effort | Maintainability | Risk |
|----------|--------|-----------------|------|
| Ansible forever | Ongoing tax | Poor | Medium–high (latent bugs) |
| Go platform-only | ~1–2 months to useful v1 | Good | Medium (cutover) |
| Go full classic | 6–18+ months | Good | High (scope) |

---

## Suggested next step (if you proceed)

**Spike (1 week):** kubebuilder scaffold + reconcile `AWXGateway` to Deployments/Services matching current templates + cert-manager Certificate + register Job in Go (or direct API client). Prove no ansible-operator dependency. No controller yet.

Success criteria: same GitOps namespace can run Go-managed gateway beside existing controller; JWT secret created without kubectl; port 80 registration always enforced.

---

## Explicit non-goals for a first Go operator

- Molecule parity with upstream awx-operator  
- Every `AWX` CR field  
- Managed Postgres operator  
- Backup/restore roles  
- OpenShift-only Routes (Gateway API / Envoy first)
