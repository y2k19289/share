# Delivery Package for Secrets Sync Lambda

This delivery folder contains a stand-alone AWS Lambda + Terraform deployment for syncing rotated Secrets Manager credentials into a target Secrets Manager secret (and optionally Kubernetes secrets).

## Structure

- `handler.py` - Lambda function logic
- `mappings.json` - mapping configuration for source secret to target secret updates
- `terraform/main.tf` - Terraform resources for Lambda, IAM, CloudTrail, EventBridge, and sample Secrets Manager secrets
- `terraform/variables.tf` - required Terraform variables
- `terraform/terraform.tfvars` - example variable values to customize for the client environment
- `terraform/build/` - output directory for the packaged Lambda ZIP file

## How to Customize

1. Update `delivery/terraform/terraform.tfvars`:
   - `aws_region`
   - `function_name`
   - `lambda_role_name`
   - `source_secret_name`
   - `initial_source_password`
   - `target_secret_name`
   - `initial_target_password`
   - `attach_vpc`, `vpc_subnet_ids`, `vpc_security_group_ids` (optional)

2. Update `delivery/mappings.json` for the client’s secret mapping.

3. Deploy from the `delivery/terraform` folder:
   ```bash
   cd delivery/terraform
   terraform init
   terraform apply -auto-approve
   ```

## Notes

- The Lambda reads `MAPPINGS_FILE` from environment variables and loads `mappings.json` from the package root.
- The Terraform package includes `handler.py` and `mappings.json` from the parent directory.
- The delivery package assumes the client will provide actual secret names and passwords in `terraform.tfvars`.
- When `target_secret_key_path` is set, the target Secrets Manager secret must already store a JSON key/value object. The Lambda updates the nested key in that JSON payload and will reject plaintext target secrets.

## Testing

1. Update the source secret using `aws secretsmanager put-secret-value`.
2. Confirm the Lambda is invoked through CloudWatch Logs.
3. Confirm the target secret is updated with the new password.
