# Cloud Armor edge policy. Tier: Standard (no Managed Protection Plus, so
# no threat-intelligence feeds / adaptive protection).
#
# Rules vary by env:
#   prod    : OWASP pre-configured WAF rules + per-IP rate-based ban + default allow
#   staging : allow only var.staging_allow_ip + default deny
#
# We deliberately avoid a ternary like `is_prod ? prod_rules : staging_rules`
# at the local level: Tofu's type-inference for object literals takes the
# concrete attribute types from the values present, so a list whose elements
# all have `expression = null` ends up with attribute type `null` (not
# `string`), which doesn't unify with prod's list. Instead, we keep two
# independently-typed lists and emit two `dynamic "rule"` blocks gated by
# `for` filters — each block only ever sees its own list shape.

locals {
  prod_armor_rules = [
    # Bypass WAF on OAuth callback paths. The provider-issued `code` is
    # opaque (e.g. Google's `4/0AVMBsJh…/…`) and routinely false-positives
    # protocolattack-v33-stable on the slashes — so this fires before the
    # OWASP rules and short-circuits to allow.
    #
    # Safety: these endpoints accept only the code + the state we minted
    # ourselves at /login (verified against an httponly cookie). No user
    # input that WAF would help screen.
    {
      kind        = "waf"
      action      = "allow"
      priority    = 500
      description = "Bypass WAF on OAuth callbacks"
      expression  = "request.path.matches('^/api/v1/auth/oauth/[^/]+/callback')"
      src_ranges  = []
    },
    # Scoped exclusion of the SQLi + RCE rules on authenticated API WRITE
    # paths (POST/PATCH/PUT under /api/v1). Same rationale as the OAuth
    # bypass above, applied to a different surface:
    #
    # Kanea is shared by humans and code-writing AI agents, so comment and
    # task/description bodies LEGITIMATELY contain SQL and code. The sqli/
    # rce rules match those bodies as injection payloads and deny(403) at
    # the edge — a silent, content-dependent failure of the core
    # collaboration interaction (issue #62).
    #
    # On these paths the edge sqli/rce body-screening protects nothing the
    # app is actually exposed to, so it is pure false-positive surface:
    #   - SQLi: every DB access is SQLAlchemy-parameterized; there is no raw
    #     SQL string-building of request data anywhere in the repos. A SQL
    #     string in a body is stored as text via a parameterized INSERT and
    #     never executed.
    #   - RCE: the app has no eval/exec/os.system/subprocess on request data.
    #     Bodies are stored as text and rendered as React-escaped plain text
    #     (no markdown/HTML parser, no dangerouslySetInnerHTML) — inert.
    #   - Pydantic v2 types/validates every field before the service layer.
    #
    # Scope is deliberately minimal: ONLY sqli + rce, ONLY on /api/v1 write
    # methods. xss / lfi / rfi / scanner / protocolattack stay armed on
    # these paths; ALL rules stay armed on reads and on the entire non-API
    # surface (marketing site, app/admin frontends, OAuth, static). If xss
    # or lfi later false-positive on legitimate code, extend the same guard
    # to them — on evidence, not preemptively.
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1000
      description = "OWASP: SQL injection (excluded on /api/v1 writes — see comment + #62)"
      expression  = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1}) && !(request.path.startsWith('/api/v1/') && (request.method == 'POST' || request.method == 'PATCH' || request.method == 'PUT'))"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1100
      description = "OWASP: cross-site scripting"
      expression  = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1200
      description = "OWASP: local file inclusion"
      expression  = "evaluatePreconfiguredWaf('lfi-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1300
      description = "OWASP: remote file inclusion"
      expression  = "evaluatePreconfiguredWaf('rfi-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      # Same scoped /api/v1-writes exclusion as the SQLi rule above (#62).
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1400
      description = "OWASP: remote code execution (excluded on /api/v1 writes — see SQLi comment + #62)"
      expression  = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1}) && !(request.path.startsWith('/api/v1/') && (request.method == 'POST' || request.method == 'PATCH' || request.method == 'PUT'))"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1500
      description = "OWASP: scanner detection"
      expression  = "evaluatePreconfiguredWaf('scannerdetection-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1600
      description = "OWASP: protocol attack"
      expression  = "evaluatePreconfiguredWaf('protocolattack-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      kind        = "waf"
      action      = "deny(403)"
      priority    = 1700
      description = "OWASP: session fixation"
      expression  = "evaluatePreconfiguredWaf('sessionfixation-v33-stable', {'sensitivity': 1})"
      src_ranges  = []
    },
    {
      kind        = "rate_limit"
      action      = "rate_based_ban"
      priority    = 2000
      description = "Per-IP rate limit: 600 req/min, 10 min ban"
      expression  = ""
      src_ranges  = ["*"]
    },
    {
      kind        = "src_ip"
      action      = "allow"
      priority    = 2147483647
      description = "Default allow"
      expression  = ""
      src_ranges  = ["*"]
    },
  ]

  # Staging rules don't need a WAF expression — drop the field entirely
  # rather than fight Tofu's null-typing.
  staging_armor_rules = [
    {
      action      = "allow"
      priority    = 1000
      description = "Allow developer IP (override via -var staging_allow_ip=…)"
      src_ranges  = [var.staging_allow_ip]
    },
    {
      action      = "deny(403)"
      priority    = 2147483647
      description = "Default deny — staging is closed by default"
      src_ranges  = ["*"]
    },
  ]
}

resource "google_compute_security_policy" "edge" {
  name = "kanea-edge-armor${local.name_suffix}"
  description = local.is_prod ? "OWASP WAF + rate limiting (Cloud Armor Standard tier)." : (
    "Staging: deny-all except ${var.staging_allow_ip}."
  )

  # ---------- Prod rules (only emitted when is_prod) ----------
  dynamic "rule" {
    for_each = [for r in local.prod_armor_rules : r if local.is_prod]
    content {
      action      = rule.value.action
      priority    = rule.value.priority
      description = rule.value.description

      match {
        # WAF rules use a CEL expression; src_ip / rate_limit rules use
        # SRC_IPS_V1 with a CIDR list. Exactly one shape is set per rule.
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

  # ---------- Staging rules (only emitted when !is_prod) ----------
  dynamic "rule" {
    for_each = [for r in local.staging_armor_rules : r if !local.is_prod]
    content {
      action      = rule.value.action
      priority    = rule.value.priority
      description = rule.value.description

      match {
        versioned_expr = "SRC_IPS_V1"
        config {
          src_ip_ranges = rule.value.src_ranges
        }
      }
    }
  }
}
