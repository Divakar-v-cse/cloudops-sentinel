output "vpc_id" {
  description = "VPC created for the Sentinel stack."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = aws_subnet.public[*].id
}

output "app_security_group_id" {
  description = "Security group attached to application hosts."
  value       = aws_security_group.app.id
}

output "instance_ids" {
  description = "Application instance IDs (empty when instance_count is 0)."
  value       = aws_instance.app[*].id
}

output "artifacts_bucket" {
  description = "Encrypted artifacts bucket name."
  value       = aws_s3_bucket.artifacts.bucket
}

output "sentinel_role_arn" {
  description = "Read-only role ARN to attach to the host running CloudOps Sentinel."
  value       = aws_iam_role.app.arn
}

output "alerts_topic_arn" {
  description = "SNS topic for CloudWatch alarms (set as SNS_TOPIC_ARN)."
  value       = aws_sns_topic.alerts.arn
}
