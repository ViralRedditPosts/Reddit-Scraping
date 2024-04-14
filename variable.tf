variable "env" {
  type = string
  default = "dev"
  description = "environment to deploy to"
}

variable "cloudwatch_state" {
  type = string
  default = "DISABLED"
  description = "Whether or not the lambda function schedule is enabled or not. Valid values are DISABLED, ENABLED, and ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENT"
}
