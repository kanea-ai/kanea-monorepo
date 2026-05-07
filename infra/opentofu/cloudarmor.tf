# Cloud Armor edge policy. Tier: Standard (no Managed Protection Plus, so
# no threat-intelligence feeds / adaptive protection).
#
# Rules vary by env:
#   prod    : OWASP pre-configured WAF rules + per-IP rate-based ban + default allow
#   staging : allow only var.staging_allow_ip + default deny
#
# A single resource address (`google_compute_security_policy.edge`) is kept
# across envs so prod state isn't disrupted; the rule set switches via
# env-keyed locals + a `dynamic "rule"` block.

locals {
  # Every rule has the same shape so the two lists share a Tofu tuple type.
  # `expression` is set on WAF rules and null elsewhere; `src_ranges` is
  # set on src_ip / rate_limit rules and null on WAF rules.
  prod_armor_rules = [
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1000
      description = "OWASP: SQL injection"
      expression  = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1100
      description = "OWASP: cross-site scripting"
      expression  = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1200
      description = "OWASP: local file inclusion"
      expression  = "evaluatePreconfiguredWaf('lfi-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1300
      description = "OWASP: remote file inclusion"
      expression  = "evaluatePreconfiguredWaf('rfi-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1400
      description = "OWASP: remote code execution"
      expression  = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1500
      description = "OWASP: scanner detection"
      expression  = "evaluatePreconfiguredWaf('scannerdetection-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1600
      description = "OWASP: protocol attack"
      expression  = "evaluatePreconfiguredWaf('protocolattack-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1700
      description = "OWASP: session fixation"
      expression  = "evaluatePreconfiguredWaf('sessionfixation-v33-stable', {'sensitivity': 1})"
      src_ranges  = null
    },
    {
      kind        = "rate_limit"
      action      = "rate_based_ban"
      priority    = 2000
      description = "Per-IP rate limit: 600 req/min, 10 min ban"
      expression  = null
      src_ranges  = ["*"]
    },
    {
      kind        = "src_ip"
      action      = "allow"
      priority    = 2147483647
      description = "Default allow"
      expression  = null
      src_ranges  = ["*"]
    },
  ]

  staging_armor_rules = [
    {
      kind        = "src_ip"
      action      = "allow"
      priority    = 1000
      description = "Allow developer IP (override via -var staging_allow_ip=…)"
      expression  = null
      src_ranges  = [var.staging_allow_ip]
    },
    {
      kind        = "src_ip"
      action      = "deny(403)"
      priority    = 2147483647
      description = "Default deny — staging is closed by default"
      expression  = null
      src_ranges  = ["*"]
    },
  ]

  armor_rules = local.is_prod ? local.prod_armor_rules : local.staging_armor_rules
}

resource "google_compute_security_policy" "edge" {
  name = "kanea-edge-armor${local.name_suffix}"
  description = local.is_prod ? "OWASP WAF + rate limiting (Cloud Armor Standard tier)." : (
    "Staging: deny-all except ${var.staging_allow_ip}."
  )

  dynamic "rule" {
    for_each = local.armor_rules
    content {
      action      = rule.value.action
      priority    = rule.value.priority
      description = rule.value.description

      match {
        # WAF rules use a CEL expression; the rest use SRC_IPS_V1 with
        # a CIDR list. The block shape is exclusive — exactly one of
        # `expr` or `versioned_expr+config` is set per rule.
        dynamic "expr" {
          for_each = rule.value.kind == "waf" ? [1] : []
          content {
            expression = rule.value.expression
          }
        }

        versioned_expr = rule.value.kind == "waf" ? null : "SRC_IPS_V1"

        dynamic "config" {
          for_each = rule.value.kind == "waf" ? [] : [1]
          content {
            src_ip_ranges = rule.value.src_ranges
          }
        }
      }

      dynamic "rate_limit_options" {
        for_each = rule.value.kind == "rate_limit" ? [1] : []
        content {
          enforce_on_key   = "IP"
          conform_action   = "allow"
          exceed_action    = "deny(429)"
          ban_duration_sec = 600
          rate_limit_threshold {
            count        = 600
            interval_sec = 60
          }
        }
      }
    }
  }
}
