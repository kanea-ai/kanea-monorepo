# Project-level override of the inherited Domain Restricted Sharing
# constraint (`constraints/iam.allowedPolicyMemberDomains`).
#
# Project-scoped, so once prod has applied this both envs benefit. Lives
# in prod state only — staging applies don't try to manage it.

resource "google_org_policy_policy" "allowed_policy_member_domains" {
  count = local.is_prod ? 1 : 0

  name   = "projects/${var.project_id}/policies/iam.allowedPolicyMemberDomains"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      allow_all = "TRUE"
    }
  }
}

moved {
  from = google_org_policy_policy.allowed_policy_member_domains
  to   = google_org_policy_policy.allowed_policy_member_domains[0]
}
