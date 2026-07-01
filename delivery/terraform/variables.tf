variable "aws_region" {
  description = "AWS region for the deployment"
  type        = string
  default     = "us-east-1"
}

variable "function_name" {
  description = "Lambda function name"
  type        = string
}

variable "lambda_role_name" {
  description = "IAM role name for the Lambda"
  type        = string
}

variable "source_secret_name" {
  description = "Source Secrets Manager secret name for rotated RDS credentials"
  type        = string
}

variable "target_secret_name" {
  description = "Target Secrets Manager secret name to update"
  type        = string
}
