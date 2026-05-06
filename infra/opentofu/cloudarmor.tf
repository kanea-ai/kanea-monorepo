# Cloud Armor edge policy — Standard tier only. We do NOT have Managed
# Protection Plus, so threat-intelligence feeds (evaluateThreatIntelligence)
# and adaptive protection are out. What works on Standard:
#   - Pre-configured WAF rules (OWASP CRS): sqli, xss, lfi, rfi, scanner, etc.
#   - Rate-based bans by client IP.
#   - Static deny lists by IP / CIDR.
resource "google_compute_security_policy" "edge" {
  name        = "kanea-edge-armor"
  description = "OWASP WAF + rate limiting (Cloud Armor Standard tier)."

  # ---------- Pre-configured OWASP WAF rules ----------
  # Sensitivity 1 = paranoia level 1 (fewest false positives). Tune up after
  # baseline traffic is observed.

  rule {
    action      = "deny(403)"
    priority    = 1000
    description = "OWASP: SQL injection"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1100
    description = "OWASP: cross-site scripting"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1200
    description = "OWASP: local file inclusion"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('lfi-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1300
    description = "OWASP: remote file inclusion"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rfi-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1400
    description = "OWASP: remote code execution"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1500
    description = "OWASP: scanner detection"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('scannerdetection-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1600
    description = "OWASP: protocol attack"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('protocolattack-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 1700
    description = "OWASP: session fixation"
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sessionfixation-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  # ---------- Rate-based ban ----------
  # 600 req / IP / minute, then 10-minute ban. Catches naïve scrapers and
  # credential-stuffing without affecting normal interactive use.
  rule {
    action      = "rate_based_ban"
    priority    = 2000
    description = "Per-IP rate limit: 600 req/min, 10 min ban"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      enforce_on_key = "IP"
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 600
        interval_sec = 60
      }
      ban_duration_sec = 600
    }
  }

  # ---------- Default ----------
  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
