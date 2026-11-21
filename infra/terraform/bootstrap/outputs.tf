output "state_bucket" {
  description = "Pass to `terraform init -backend-config=bucket=...` in envs/*"
  value       = aws_s3_bucket.tfstate.bucket
}

output "registry" {
  description = "Image registry (images are <registry>/alex-<name>:<tag>)"
  value       = split("/", aws_ecr_repository.image["api"].repository_url)[0]
}

output "deploy_role_arn" {
  description = "Set as the GitHub Actions variable AWS_DEPLOY_ROLE_ARN"
  value       = aws_iam_role.deploy.arn
}
