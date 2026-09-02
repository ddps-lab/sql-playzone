import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EC2 = ROOT / "IaC" / "ec2" / "ec2.tf"
EC2_VARS = ROOT / "IaC" / "ec2" / "var.tf"
ROOT_VARS = ROOT / "IaC" / "var.tf"
ROOT_MAIN = ROOT / "IaC" / "main.tf"
README = ROOT / "IaC" / "README.md"


def top_level_block(text: str, header: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(header)} \{{\n(.*?)^\}}", text)
    if not match:
        raise AssertionError(f"block {header} not found")
    return match.group(1)


class ASGExamReadinessTests(unittest.TestCase):
    def test_first_boot_budget_is_five_minutes(self):
        asg = top_level_block(EC2.read_text(), 'resource "aws_autoscaling_group" "asg"')
        self.assertRegex(asg, r'health_check_type\s*=\s*"ELB"')
        self.assertRegex(asg, r"health_check_grace_period\s*=\s*300\b")
        self.assertRegex(asg, r"instance_warmup\s*=\s*300\b")

    def test_alb_health_check_uses_the_healthcheck_endpoint(self):
        # The index page is gated by the exam-browser switch; /healthcheck is
        # exempt in both plugins and reports database and config health.
        tg = top_level_block(EC2.read_text(), 'resource "aws_lb_target_group" "tg"')
        self.assertRegex(tg, r'path\s*=\s*"/healthcheck"')
        self.assertRegex(tg, r'matcher\s*=\s*"200"')

    def test_apply_does_not_revert_runtime_capacity(self):
        asg = top_level_block(EC2.read_text(), 'resource "aws_autoscaling_group" "asg"')
        self.assertRegex(asg, r"ignore_changes\s*=\s*\[desired_capacity, min_size\]")

    def test_exam_windows_become_scheduled_actions(self):
        ec2 = EC2.read_text()
        locals_block = ec2[ec2.index("# Scheduled pre-scaling for exams and quizzes"):]
        self.assertIn('timeadd("${window.start}Z", "-9h")', locals_block)
        self.assertIn('timeadd("${window.end}Z", "-9h")', locals_block)
        self.assertIn("timecmp(window.start_time, plantimestamp()) > 0", locals_block)
        self.assertIn("timecmp(window.end_time, plantimestamp()) > 0", locals_block)

        scale_out = top_level_block(ec2, 'resource "aws_autoscaling_schedule" "exam_scale_out"')
        self.assertRegex(scale_out, r"for_each\s*=\s*local\.exam_scale_out")
        self.assertRegex(scale_out, r"start_time\s*=\s*each\.value\.start_time")
        self.assertRegex(scale_out, r"min_size\s*=\s*each\.value\.capacity")
        self.assertRegex(scale_out, r"desired_capacity\s*=\s*each\.value\.capacity")
        self.assertRegex(scale_out, r"max_size\s*=\s*-1\b")

        scale_in = top_level_block(ec2, 'resource "aws_autoscaling_schedule" "exam_scale_in"')
        self.assertRegex(scale_in, r"for_each\s*=\s*local\.exam_scale_in")
        self.assertRegex(scale_in, r"start_time\s*=\s*each\.value\.end_time")
        self.assertRegex(scale_in, r"min_size\s*=\s*var\.asg_min_size")
        self.assertRegex(scale_in, r"max_size\s*=\s*-1\b")
        self.assertRegex(scale_in, r"desired_capacity\s*=\s*-1\b")

    def test_exam_windows_are_wired_from_the_root_module(self):
        root_vars = ROOT_VARS.read_text()
        exam_windows = top_level_block(root_vars, 'variable "exam_windows"')
        self.assertRegex(exam_windows, r"default\s*=\s*\[\]")
        self.assertEqual(exam_windows.count("validation {"), 5)
        self.assertIn('try(timecmp("${window.start}Z", "${window.end}Z") < 0, false)', exam_windows)
        self.assertIn("distinct(var.exam_windows[*].name)", exam_windows)
        self.assertIn("window.capacity <= var.asg_max_size", exam_windows)
        self.assertIn('timecmp("${a.end}Z", "${b.start}Z") < 0', exam_windows)
        self.assertIn("must not overlap", exam_windows)

        module_vars = EC2_VARS.read_text()
        self.assertIn('variable "exam_windows"', module_vars)
        self.assertRegex(ROOT_MAIN.read_text(), r"exam_windows\s*=\s*var\.exam_windows")

    def test_scale_out_defaults_to_on_demand(self):
        root_vars = ROOT_VARS.read_text()
        ratio = top_level_block(root_vars, 'variable "on_demand_percentage_above_base"')
        self.assertRegex(ratio, r"default\s*=\s*100\b")
        self.assertIn("<= 100", ratio)

    def test_readme_explains_exam_windows(self):
        readme = README.read_text()
        self.assertIn("exam_windows", readme)
        self.assertIn("KST", readme)
        self.assertIn("health_check_grace_period", readme)


if __name__ == "__main__":
    unittest.main()
