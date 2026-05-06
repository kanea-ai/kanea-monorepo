# Project-level override of the inherited Domain Restricted Sharing
# constraint (`constraints/iam.allowedPolicyMemberDomains`).
#
# Without this override the project inherits the org default, which blocks
# IAM bindings that name members outside the allowed customer (notably
# `allUsers` and `allAuthenticatedUsers`). That blocks granting public
# `roles/run.invoker` on the public Cloud Run services, which is what makes
# them reachable through the load balancer.
#
# Scope: project-only. The org-level constraint stays in force everywhere
# else; this is the minimum relaxation needed to run a public website out
# of kanea-prod-env.

resource "google_org_policy_policy" "allowed_policy_member_domains" {
  name   = "projects/${var.project_id}/policies/iam.allowedPolicyMemberDomains"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      allow_all = "TRUE"
    }
  }
}
