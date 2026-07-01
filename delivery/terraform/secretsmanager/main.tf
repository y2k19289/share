data "aws_secretsmanager_secret" "source" {
  name = var.source_secret_name
}

data "aws_secretsmanager_secret" "target" {
  name = var.target_secret_name
}
