# Settings generated here go into SSM Parameter Store as SecureStrings
# (encrypted with the account's aws/ssm key). The app server's deploy script
# turns each folder into an env file:
#
#   <prefix>/common/*          every service (DATABASE_URL, REDIS_PASSWORD)
#   <prefix>/avatar/*          API + agent (AUTH_SECRET, S3_*, and the API keys
#                              you add with scripts/aws/put-secrets.sh)
#   <prefix>/worker/*          worker (API keys you add)
#   <prefix>/sandbox-client/*  worker's TLS client certificate for the sandbox
#   <prefix>/sandbox-server/*  the sandbox Docker daemon's TLS certificate
#   <prefix>/deploy/*          non-secret pointers for the deploy workflow
#
# These values are also in the Terraform state, which is why the state bucket
# is private and encrypted.

resource "random_password" "auth_secret" {
  length  = 48
  special = false
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

locals {
  generated = {
    "common/DATABASE_URL"   = "postgresql://alex:${random_password.db.result}@${aws_db_instance.main.address}:5432/alex?ssl=require"
    "common/REDIS_PASSWORD" = random_password.redis.result
    "avatar/AUTH_SECRET"    = random_password.auth_secret.result
    "avatar/S3_BUCKET"      = aws_s3_bucket.recordings.bucket
    "avatar/S3_REGION"      = var.aws_region
    "avatar/S3_ACCESS_KEY"  = aws_iam_access_key.recordings.id
    "avatar/S3_SECRET_KEY"  = aws_iam_access_key.recordings.secret
  }
}

resource "aws_ssm_parameter" "generated" {
  for_each = local.generated
  name     = "${local.ssm_prefix}/${each.key}"
  type     = "SecureString"
  value    = each.value
}

resource "aws_ssm_parameter" "deploy" {
  for_each = {
    "instance-id" = aws_instance.app.id
    "ops-bucket"  = aws_s3_bucket.ops.bucket
    "registry"    = local.registry
  }
  name  = "${local.ssm_prefix}/deploy/${each.key}"
  type  = "String"
  value = each.value
}

# ---- TLS between the worker and the sandbox Docker daemon -------------------------
# Mutual TLS: the daemon accepts only clients with a certificate from this CA.

resource "tls_private_key" "sandbox_ca" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_self_signed_cert" "sandbox_ca" {
  private_key_pem       = tls_private_key.sandbox_ca.private_key_pem
  is_ca_certificate     = true
  validity_period_hours = 24 * 365 * 5
  allowed_uses          = ["cert_signing", "crl_signing", "digital_signature"]
  subject {
    common_name = "${local.name} sandbox CA"
  }
}

resource "tls_private_key" "sandbox_server" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_cert_request" "sandbox_server" {
  private_key_pem = tls_private_key.sandbox_server.private_key_pem
  ip_addresses    = [local.sandbox_private_ip]
  subject {
    common_name = "sandbox"
  }
}

resource "tls_locally_signed_cert" "sandbox_server" {
  cert_request_pem      = tls_cert_request.sandbox_server.cert_request_pem
  ca_private_key_pem    = tls_private_key.sandbox_ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.sandbox_ca.cert_pem
  validity_period_hours = 24 * 365 * 5
  allowed_uses          = ["server_auth", "digital_signature", "key_encipherment"]
}

resource "tls_private_key" "sandbox_client" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_cert_request" "sandbox_client" {
  private_key_pem = tls_private_key.sandbox_client.private_key_pem
  subject {
    common_name = "worker"
  }
}

resource "tls_locally_signed_cert" "sandbox_client" {
  cert_request_pem      = tls_cert_request.sandbox_client.cert_request_pem
  ca_private_key_pem    = tls_private_key.sandbox_ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.sandbox_ca.cert_pem
  validity_period_hours = 24 * 365 * 5
  allowed_uses          = ["client_auth", "digital_signature", "key_encipherment"]
}

resource "aws_ssm_parameter" "sandbox_server" {
  for_each = {
    ca   = tls_self_signed_cert.sandbox_ca.cert_pem
    cert = tls_locally_signed_cert.sandbox_server.cert_pem
    key  = tls_private_key.sandbox_server.private_key_pem
  }
  name  = "${local.ssm_prefix}/sandbox-server/${each.key}"
  type  = "SecureString"
  value = each.value
}

resource "aws_ssm_parameter" "sandbox_client" {
  for_each = {
    ca   = tls_self_signed_cert.sandbox_ca.cert_pem
    cert = tls_locally_signed_cert.sandbox_client.cert_pem
    key  = tls_private_key.sandbox_client.private_key_pem
  }
  name  = "${local.ssm_prefix}/sandbox-client/${each.key}"
  type  = "SecureString"
  value = each.value
}
