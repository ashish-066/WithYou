variable "project" {
  type    = string
  default = "alex"
}

variable "aws_region" {
  type    = string
  default = "ap-south-1" # Mumbai, near the LiveKit Cloud India South region
}

variable "github_repo" {
  description = "owner/name of the GitHub repository whose main branch may deploy"
  type        = string
  default     = "ashish-066/letsee"
}

variable "github_sub_prefix" {
  description = <<-EOT
    Start of the OIDC "sub" claim GitHub sends for this repository. Repositories using
    GitHub's immutable subject format send owner@id/name@id instead of owner/name; check with
    `gh api repos/<owner>/<name>/actions/oidc/customization/sub` (field sub_claim_prefix).
    Empty means the classic "repo:<github_repo>" form.
  EOT
  type        = string
  default     = "repo:ashish-066@177954756/letsee@1442146401"
}
