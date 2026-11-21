# recordings: interview videos (private, encrypted, versioned; viewers get
#             15-minute signed links from the API)
# ops:        release bundles the deploy workflow uploads for the app server

resource "aws_s3_bucket" "recordings" {
  bucket = "${local.name}-recordings-${local.account_id}"
}

resource "aws_s3_bucket" "ops" {
  bucket        = "${local.name}-ops-${local.account_id}"
  force_destroy = true # holds only re-creatable release bundles
}

locals {
  buckets = {
    recordings = aws_s3_bucket.recordings
    ops        = aws_s3_bucket.ops
  }
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each                = local.buckets
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "all" {
  for_each = local.buckets
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = local.buckets
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  for_each = local.buckets
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each   = local.buckets
  bucket     = each.value.id
  policy     = data.aws_iam_policy_document.tls_only[each.key].json
  depends_on = [aws_s3_bucket_public_access_block.all]
}

resource "aws_s3_bucket_versioning" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "ops" {
  bucket = aws_s3_bucket.ops.id
  rule {
    id     = "expire-releases"
    status = "Enabled"
    filter {
      prefix = "releases/"
    }
    expiration {
      days = 90
    }
  }
}

# LiveKit Cloud's egress uploads recordings from outside AWS, so it needs
# access keys. This user can only read and write the recordings bucket. The
# API uses the same keys to sign viewing links.
resource "aws_iam_user" "recordings" {
  name = "${local.name}-recordings"
}

data "aws_iam_policy_document" "recordings" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"]
    resources = ["${aws_s3_bucket.recordings.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.recordings.arn]
  }
}

resource "aws_iam_user_policy" "recordings" {
  name   = "recordings"
  user   = aws_iam_user.recordings.name
  policy = data.aws_iam_policy_document.recordings.json
}

resource "aws_iam_access_key" "recordings" {
  user = aws_iam_user.recordings.name
}
