output "app_public_ip" {
  description = "Point the domain's DNS A record here"
  value       = aws_eip.app.public_ip
}

output "app_instance_id" {
  description = "For `aws ssm start-session --target ...`"
  value       = aws_instance.app.id
}

output "sandbox_instance_id" {
  value = aws_instance.sandbox.id
}

output "ssm_prefix" {
  description = "Where this environment's settings live in SSM Parameter Store"
  value       = local.ssm_prefix
}

output "recordings_bucket" {
  value = aws_s3_bucket.recordings.bucket
}

output "database_endpoint" {
  value = aws_db_instance.main.address
}
