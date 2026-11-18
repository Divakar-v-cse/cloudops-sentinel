data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "AllowEc2AssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.project_name}-${var.environment}-app"
  description        = "Read-only role used by CloudOps Sentinel to inventory AWS resources"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "read_only_inventory" {
  statement {
    sid    = "DescribeCompute"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeVolumes",
      "ec2:DescribeRegions",
      "ec2:DescribeTags",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ReadStorageConfiguration"
    effect = "Allow"
    actions = [
      "s3:ListAllMyBuckets",
      "s3:GetBucketLocation",
      "s3:GetBucketAcl",
      "s3:GetBucketPolicy",
      "s3:GetBucketVersioning",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetEncryptionConfiguration",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "InspectIdentityPolicies"
    effect = "Allow"
    actions = [
      "iam:ListPolicies",
      "iam:ListUsers",
      "iam:ListRoles",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:GetAccountAuthorizationDetails",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ReadMetricsAndBilling"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "logs:DescribeLogGroups",
      "ce:GetCostAndUsage",
      "ce:GetCostForecast",
      "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "read_only_inventory" {
  name        = "${var.project_name}-${var.environment}-read-only"
  description = "Least-privilege read access for CloudOps Sentinel inventory and analyses"
  policy      = data.aws_iam_policy_document.read_only_inventory.json
}

resource "aws_iam_role_policy_attachment" "read_only_inventory" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.read_only_inventory.arn
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-${var.environment}-app"
  role = aws_iam_role.app.name
}
