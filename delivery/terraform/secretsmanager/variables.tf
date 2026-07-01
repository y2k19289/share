variable "source_secret_name" {
  description = "Source Secrets Manager secret name for rotated RDS credentials"
  type        = string
}

variable "target_secret_name" {
  description = "Target Secrets Manager secret name to update"
  type        = string
}
