variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "aws_region" {
  description = "AWS region for CloudTrail bucket naming"
  type        = string
  default     = "us-east-1"
}
