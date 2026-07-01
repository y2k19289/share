output "lambda_arn" {
  value = aws_lambda_function.update_eks_secrets.arn
}

output "lambda_name" {
  value = aws_lambda_function.update_eks_secrets.function_name
}
