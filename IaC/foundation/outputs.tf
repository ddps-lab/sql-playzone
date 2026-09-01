output "artifact_prefix" {
  value = var.artifact_prefix
}

output "ctfd_repository_name" {
  value = aws_ecr_repository.ctfd.name
}

output "sql_judge_repository_name" {
  value = aws_ecr_repository.sql_judge.name
}

output "packer_builder_instance_profile" {
  value = aws_iam_instance_profile.packer_builder.name
}
