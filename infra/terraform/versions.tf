terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configure remote state before using this in a shared environment.
  # backend "s3" {
  #   bucket         = "example-terraform-state"
  #   key            = "cloudops-sentinel/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "cloudops-sentinel"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
