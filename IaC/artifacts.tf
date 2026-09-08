data "aws_ssm_parameter" "current_release" {
  count = var.artifact_release_id == null ? 1 : 0
  name  = "${local.artifact_namespace}/channels/${var.artifact_channel}/current"
}

locals {
  selected_release_id = var.artifact_release_id != null ? var.artifact_release_id : data.aws_ssm_parameter.current_release[0].value
}

data "aws_ssm_parameter" "release_manifest" {
  name = "${local.artifact_namespace}/releases/${local.selected_release_id}"
}

locals {
  release_manifest = jsondecode(data.aws_ssm_parameter.release_manifest.value)
}

check "release_manifest" {
  assert {
    condition = (
      try(local.release_manifest.schema_version, null) == 1 &&
      try(local.release_manifest.release_id, null) == local.selected_release_id &&
      try(local.release_manifest.channel, null) == var.artifact_channel &&
      can(regex("^ami-[0-9a-f]+$", try(local.release_manifest.ami_id, ""))) &&
      can(regex("@sha256:[0-9a-f]{64}$", try(local.release_manifest.ctfd_image, ""))) &&
      can(regex("@sha256:[0-9a-f]{64}$", try(local.release_manifest.sql_judge_image, "")))
    )
    error_message = "The selected artifact manifest is invalid or belongs to another channel."
  }
}
