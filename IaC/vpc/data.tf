# 사용 가능한 availability zone 동적으로 aws api 를 통해
# 가져오게 함
data "aws_availability_zones" "region_azs" {
  state = "available"
  filter {
    name = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}