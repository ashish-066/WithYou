variable "project" {
  type    = string
  default = "alex"
}

variable "environment" {
  description = "staging or production"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "aws_region" {
  type = string
}

variable "domain" {
  description = "Public hostname, e.g. app.example.com. Point its DNS A record at the app_public_ip output; Caddy then gets a TLS certificate."
  type        = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "app_instance_type" {
  description = "Runs Caddy, frontend, API, agent, worker and Redis"
  type        = string
  default     = "t3.xlarge"
}

variable "app_volume_gb" {
  type    = number
  default = 60
}

variable "sandbox_instance_type" {
  description = "Runs only candidate code containers (gVisor)"
  type        = string
  default     = "t3.small"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "protect_data" {
  description = "Deletion protection on the database and a final snapshot on destroy. Keep true for production."
  type        = bool
  default     = true
}
