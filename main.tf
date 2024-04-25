terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "< 6.0"
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
    name      = "viralredditposts"
    region    = "us-east-2"
    pyversion = "3.12"  # used for the lambda install
  }
}

# get account id
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# zip the lambda function
# resource "null_resource" "zip_function" {
#   # rebuild zip each time, this is low cost and good for forcing it to upload each terraform apply
#   triggers = {
#     build_number = timestamp()
#   }
#   provisioner "local-exec" {
#     command    = "./scripts/zipLambdaFunction.sh -f get_reddit_data_function"
#     on_failure = fail # OR continue
#   }
# }

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "./lambda_functions/get_reddit_data_function/"
  output_path = "./scripts/zippedLambdaFunction/get_reddit_data_function.zip"
}

# zip the PRAW and boto3 packages
resource "null_resource" "zip_python_packages" {
  # this a bit slow but this forces this to rerun each time, 
  # it was easier than trying to get it to track if the zip was deleted for an environment change
  triggers = {
    build_number = timestamp()
  }
  provisioner "local-exec" {
    command    = "source venv/bin/activate && ./scripts/zipPythonPackage.sh praw==7.7.0 boto3==1.26.117 git+https://github.com/ViralRedditPosts/Utils.git@main"
    on_failure = fail # OR continue
  }
}

# add PRAW zip to S3
resource "aws_s3_object" "move_PRAW_zip" {
  depends_on = [null_resource.zip_python_packages]

  bucket = "packages-${var.info.name}-${var.env}-${local.account_id}"
  key    = "praw==7.7.0.zip"
  source = "./scripts/zippedPythonPackages/praw==7.7.0/praw==7.7.0.zip"
  tags = {
    Name        = "praw-zip"
    Environment = "${var.env}"
    Project     = "viral-reddit-posts"
  }
}

# add boto3 zip to S3
resource "aws_s3_object" "move_boto3_zip" {
  depends_on = [null_resource.zip_python_packages]

  bucket = "packages-${var.info.name}-${var.env}-${local.account_id}"
  key    = "boto3==1.26.117.zip"
  source = "./scripts/zippedPythonPackages/boto3==1.26.117/boto3==1.26.117.zip"
  tags = {
    Name        = "boto3-zip"
    Environment = "${var.env}"
    Project     = "viral-reddit-posts"
  }
}

# add git+https://github.com/ViralRedditPosts/Utils.git@main to S3
resource "aws_s3_object" "move_utils_zip" {
  depends_on = [null_resource.zip_python_packages]

  bucket = "packages-${var.info.name}-${var.env}-${local.account_id}"
  key    = "Utils.git@main.zip"
  source = "./scripts/zippedPythonPackages/Utils.git@main/Utils.git@main.zip"
  tags = {
    Name        = "utils-zip"
    Environment = "${var.env}"
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
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "dynamodb:DescribeTable",
      "dynamodb:BatchWriteItem"
    ]
    resources = [
      "arn:aws:s3:::data-${var.info.name}-${var.env}-${local.account_id}",
      "arn:aws:s3:::data-${var.info.name}-${var.env}-${local.account_id}/*",
      "arn:aws:dynamodb:${var.info.region}:${local.account_id}:table/hot-${var.env}",
      "arn:aws:dynamodb:${var.info.region}:${local.account_id}:table/rising-${var.env}"
    ]
  }
}

# create role
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role
resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam-for-lambda-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json # Policy that grants an entity permission to assume the role.

  inline_policy {
    name   = "test-policy"
    policy = data.aws_iam_policy_document.inline_policy.json
  }

  tags = {
    Environment = "${var.env}"
    Project     = "viral-reddit-posts"
  }
}

resource "aws_lambda_layer_version" "praw_layer" {
  depends_on = [aws_s3_object.move_PRAW_zip]
  # you either have to specify a local filename or the s3 object
  # https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_layer_version
  # filename   = "lambda_layer_payload.zip"
  s3_bucket                = "packages-${var.info.name}-${var.env}-${local.account_id}"
  s3_key                   = "praw==7.7.0.zip"
  layer_name               = "praw-7_7_0"
  description              = "python binaries for praw==7.7.0 library"
  compatible_architectures = ["x86_64"]
  compatible_runtimes      = ["python${var.info.pyversion}"]
}

resource "aws_lambda_layer_version" "boto3_layer" {
  depends_on = [aws_s3_object.move_boto3_zip]
  # you either have to specify a local filename or the s3 object
  # https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_layer_version
  # filename   = "lambda_layer_payload.zip"
  s3_bucket                = "packages-${var.info.name}-${var.env}-${local.account_id}"
  s3_key                   = "boto3==1.26.117.zip"
  layer_name               = "boto3-1_26_117"
  description              = "python binaries for boto3==1.26.117 library"
  compatible_architectures = ["x86_64"]
  compatible_runtimes      = ["python${var.info.pyversion}"]
}

resource "aws_lambda_layer_version" "utils_layer" {
  depends_on = [aws_s3_object.move_boto3_zip]
  # you either have to specify a local filename or the s3 object
  # https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_layer_version
  # filename   = "lambda_layer_payload.zip"
  s3_bucket                = "packages-${var.info.name}-${var.env}-${local.account_id}"
  s3_key                   = "Utils.git@main.zip"
  layer_name               = "utils_layer"
  description              = "python binaries for Utils.git@main library"
  compatible_architectures = ["x86_64"]
  compatible_runtimes      = ["python${var.info.pyversion}"]
}

# make lambda function
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function
resource "aws_lambda_function" "lambda_function" {
  # depends_on = [resource.null_resource.zip_function]

  filename      = "./scripts/zippedLambdaFunction/get_reddit_data_function.zip"
  function_name = "lambda-reddit-scraping-${var.env}"
  role          = aws_iam_role.iam_for_lambda.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python${var.info.pyversion}"
  timeout       = 60

  ephemeral_storage {
    size = 512 # Min 512 MB and the Max 10240 MB
  }

  layers = [
    aws_lambda_layer_version.praw_layer.arn, 
    aws_lambda_layer_version.boto3_layer.arn,
    aws_lambda_layer_version.utils_layer.arn,
    ]

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      AWS_BUCKET = "data-${var.info.name}-${var.env}-${local.account_id}",
      ENV        = "${var.env}"
    }
  }
  tags = {
    Environment = "${var.env}"
    Project     = "viral-reddit-posts"
  }
}

# Attach event trigger to Lambda Function, see https://stackoverflow.com/questions/35895315/use-terraform-to-set-up-a-lambda-function-triggered-by-a-scheduled-event-source
resource "aws_cloudwatch_event_rule" "every_one_minute" {
    name = "every-one-minute"
    description = "Fires every one minute"
    schedule_expression = "rate(1 minute)"
    state=var.cloudwatch_state
}

resource "aws_cloudwatch_event_target" "scrape_reddit_every_minute" {
    rule = aws_cloudwatch_event_rule.every_one_minute.name
    target_id = "scrape_reddit"
    arn = aws_lambda_function.lambda_function.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_to_call_lambda_function" {
    statement_id = "AllowExecutionFromCloudWatch"
    action = "lambda:InvokeFunction"
    function_name = aws_lambda_function.lambda_function.function_name
    principal = "events.amazonaws.com"
    source_arn = aws_cloudwatch_event_rule.every_one_minute.arn
}
