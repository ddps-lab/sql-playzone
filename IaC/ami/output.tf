output "ctfd_ami_arm_id" {
  value = local.ami_exists_arm ? data.aws_ami_ids.existing_ctfd_ami_arm.ids[0] : aws_ami_from_instance.ctfd_ami_arm[0].id
}