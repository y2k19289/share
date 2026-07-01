data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../.."
  output_path = "${path.root}/build/update-eks-secrets.zip"
  excludes = [
    "terraform/**",
    "*.tfstate",
    "*.tfstate.backup",
    ".terraform/**",
    "terraform.tfvars",
    "terraform.tfvars.json",
    "*.tfignore",
    "*.zip",
    "**/__pycache__/**",
    "**/*.pyc"
  ]
}

resource "aws_lambda_function" "update_eks_secrets" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = var.function_name
  role             = var.role_arn
  handler          = "lambda/handler.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      MAPPINGS_FILE = "/var/task/mappings.json"
    }
  }
}
