# Two servers: the app server (all services via docker compose) and the
# sandbox server (only candidate code). IMDSv2 with hop limit 1, so containers
# can't read the instance role's credentials.

locals {
  # Fixed address so the sandbox's TLS certificate can name it before it exists
  sandbox_private_ip = cidrhost(aws_subnet.public[0].cidr_block, 20)
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# ---- App server -----------------------------------------------------------------

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "app" {
  statement {
    sid     = "ReadOwnSettings"
    actions = ["ssm:GetParametersByPath", "ssm:GetParameter"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/common",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/common/*",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/avatar",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/avatar/*",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/worker",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/worker/*",
      "arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/sandbox-client/*",
    ]
  }
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "EcrPull"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = ["arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${var.project}-*"]
  }
  statement {
    sid       = "ReadReleases"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.ops.arn, "${aws_s3_bucket.ops.arn}/releases/*"]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "app"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.app_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  root_block_device {
    volume_type = "gp3"
    volume_size = var.app_volume_gb
    encrypted   = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/templates/app-user-data.sh.tftpl", {
    environment  = var.environment
    aws_region   = var.aws_region
    ssm_prefix   = local.ssm_prefix
    registry     = local.registry
    domain       = var.domain
    sandbox_host = local.sandbox_private_ip
  })

  tags = {
    Name = "${local.name}-app"
    Role = "${var.project}-app" # the deploy role may run commands only on these
  }

  lifecycle {
    # A newer Ubuntu image or edited bootstrap script shouldn't replace a running server
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${local.name}-app" }
}

# ---- Sandbox server ---------------------------------------------------------------

resource "aws_iam_role" "sandbox" {
  name               = "${local.name}-sandbox"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "sandbox_ssm" {
  role       = aws_iam_role.sandbox.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "sandbox" {
  statement {
    sid       = "ReadServerCertificate"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter${local.ssm_prefix}/sandbox-server/*"]
  }
}

resource "aws_iam_role_policy" "sandbox" {
  name   = "sandbox"
  role   = aws_iam_role.sandbox.id
  policy = data.aws_iam_policy_document.sandbox.json
}

resource "aws_iam_instance_profile" "sandbox" {
  name = "${local.name}-sandbox"
  role = aws_iam_role.sandbox.name
}

resource "aws_instance" "sandbox" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.sandbox_instance_type
  subnet_id              = aws_subnet.public[0].id
  private_ip             = local.sandbox_private_ip
  vpc_security_group_ids = [aws_security_group.sandbox.id]
  iam_instance_profile   = aws_iam_instance_profile.sandbox.name

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # No secrets in user data: the server fetches its TLS key from SSM at boot
  user_data = templatefile("${path.module}/templates/sandbox-user-data.sh.tftpl", {
    aws_region = var.aws_region
    ssm_prefix = local.ssm_prefix
  })

  tags = {
    Name = "${local.name}-sandbox"
    Role = "${var.project}-sandbox"
  }

  depends_on = [aws_ssm_parameter.sandbox_server]

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}
