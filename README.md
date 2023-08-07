# Reddit Scraping

The purpose of this repo is to deploy AWS Lambda function that scrapes rising and hot reddit posts.

# How to use

1. First ensure the DynamoDB tables are set up via [DynamoDB-Setup](https://github.com/ViralRedditPosts/DynamoDB-Setup).
2. Installs - see the [prerequisites section on this page](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/aws-build#prerequisites) for additional information, the steps are essentially:
    1. Install Terraform CLI
    2. Install AWS CLI and run `aws configure` and enter in your aws credentials.
3. Clone this repository 
4. From within this repository run the following:
  
    ```sh
    terraform init
    terraform apply
    ```
    If you don't want to apply the changes to your aws account you can instead run `terraform plan`.