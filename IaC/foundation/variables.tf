variable "artifact_prefix" {
  description = "Semester-scoped prefix for artifact repositories and builder resources"
  type        = string
  default     = "sql-2026-s2"

  validation {
    condition     = length(var.artifact_prefix) <= 28 && can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.artifact_prefix))
    error_message = "artifact_prefix must be at most 28 characters and contain lowercase letters, numbers, and internal hyphens."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "aws_profile" {
  description = "AWS CLI profile used by Terraform"
  type        = string
  default     = "hyu-ddps"
}
