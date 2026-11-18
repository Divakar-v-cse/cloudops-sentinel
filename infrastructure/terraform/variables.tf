variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be dev, staging or production."
  }
}

variable "project_name" {
  description = "Prefix used for resource names."
  type        = string
  default     = "cloudops-sentinel"
}

variable "vpc_cidr" {
  description = "CIDR block for the Sentinel VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "allowed_admin_cidr" {
  description = "Trusted CIDR allowed to reach SSH/HTTPS. Never use 0.0.0.0/0 here."
  type        = string
  default     = "10.0.0.0/8"
}

variable "instance_type" {
  description = "EC2 instance type for the application host."
  type        = string
  default     = "t3.small"
}

variable "instance_count" {
  description = "Number of application hosts. Defaults to 0 so a plan creates no compute cost."
  type        = number
  default     = 0
}

variable "root_volume_gb" {
  description = "Encrypted root volume size in GiB."
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Optional email for CloudWatch alarm notifications. Leave empty to skip the subscription."
  type        = string
  default     = ""
}

variable "cpu_alarm_threshold" {
  description = "CPU percentage that triggers the high-utilisation alarm."
  type        = number
  default     = 85
}
