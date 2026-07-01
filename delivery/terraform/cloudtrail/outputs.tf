output "cloudtrail_bucket" {
  value = aws_s3_bucket.cloudtrail_bucket.bucket
}

output "cloudtrail_name" {
  value = aws_cloudtrail.secrets_trail.name
}
