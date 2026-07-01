terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

module "iam" {
  source = "./iam"

  lambda_role_name = var.lambda_role_name
}

module "lambda" {
  source = "./lambda"

  function_name = var.function_name
  role_arn      = module.iam.role_arn
}

module "eventbridge" {
  source = "./eventbridge"

  lambda_arn  = module.lambda.lambda_arn
  lambda_name = module.lambda.lambda_name
}

module "cloudtrail" {
  source = "./cloudtrail"

  account_id = data.aws_caller_identity.current.account_id
  aws_region = var.aws_region
}

module "secretsmanager" {
  source = "./secretsmanager"

  source_secret_name = var.source_secret_name
  target_secret_name = var.target_secret_name
}

output "lambda_function_name" {
  value = module.lambda.lambda_name
}

output "cloudtrail_bucket" {
  value = module.cloudtrail.cloudtrail_bucket
}

output "cloudtrail_name" {
  value = module.cloudtrail.cloudtrail_name
}
