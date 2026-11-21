# production environment. First time:
#   terraform init -backend-config="bucket=<state_bucket output of bootstrap>"
#   cp terraform.tfvars.example terraform.tfvars   # then edit
#   terraform plan -out plan.tfplan && terraform apply plan.tfplan

terraform {
  required_version = ">= 1.10"
  backend "s3" {
    key          = "production/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "alex"
      Environment = "production"
      ManagedBy   = "terraform"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "domain" {
  type = string
}

module "stack" {
  source            = "../../modules/stack"
  environment       = "production"
  aws_region        = var.aws_region
  domain            = var.domain
  vpc_cidr          = "10.30.0.0/16"
  app_instance_type = "t3.xlarge"
  protect_data      = true
}

output "app_public_ip" {
  value = module.stack.app_public_ip
}

output "app_instance_id" {
  value = module.stack.app_instance_id
}

output "sandbox_instance_id" {
  value = module.stack.sandbox_instance_id
}

output "ssm_prefix" {
  value = module.stack.ssm_prefix
}
