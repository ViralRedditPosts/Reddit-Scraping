terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }

  required_version = ">= 1.2.0"
}

provider "aws" {
  region = "us-east-2"
}

variable "info" {
  type = map(string)
  default = {
    name = "viralredditposts"
    env  = "dev"
  }
}

# get account id
data "aws_caller_identity" "current" {}

locals {
    account_id = data.aws_caller_identity.current.account_id
}

# zip the lambda function
resource "null_resource" "zip_function" {
  provisioner "local-exec" {
    command    = "./scripts/zipLambdaFunction.sh -f getRedditDataFunction"
    on_failure = fail # OR continue
  }
}

# zip the PRAW package
resource "null_resource" "zip_PRAW" {
  provisioner "local-exec" {
    command    = "./scripts/zipPythonPackage.sh -p praw -s packages-${var.info.name}-${var.info.env}-${local.account_id}"
    on_failure = fail # OR continue
  }
}

# add PRAW zip to S3
resource "aws_s3_object" "move_PRAW_zip" {
  depends_on = [ null_resource.zip_PRAW ]

  bucket = "packages-${var.info.name}-${var.info.env}-${local.account_id}" 
  key    = "praw.zip"
  source = "./scripts/zippedPythonPackages/praw/praw.zip"
  tags = {
    Name        = "praw-zip"
    Environment = "${var.info.env}"
    Project     = "viral-reddit-posts"
  }
}

# define policy for attaching role
data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = [
      "sts:AssumeRole",
    ]
  }
}

data "aws_iam_policy_document" "inline_policy" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::data-${var.info.name}-${var.info.env}/*"]
  }
}

# create role
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role
resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam-for-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json  # Policy that grants an entity permission to assume the role.

  inline_policy {
    name   = "test-policy"
    policy = data.aws_iam_policy_document.inline_policy.json
  }

  tags = {
    Environment = "${var.info.env}"
    Project     = "viral-reddit-posts"
  }
}

# make lambda function
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function
resource "aws_lambda_function" "test_lambda" {
  depends_on = [
    resource.null_resource.zip_function
  ]

  filename      = "./scripts/zippedLambdaFunction/getRedditDataFunction.zip"
  function_name = "lambda-reddit-scraping-${var.info.env}"
  role          = aws_iam_role.iam_for_lambda.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.7"
  timeout       = 60

  ephemeral_storage {
    size = 512 # Min 512 MB and the Max 10240 MB
  }

  tags = {
    Environment = "${var.info.env}"
    Project     = "viral-reddit-posts"
  }
}
