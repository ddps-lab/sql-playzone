import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USER_DATA = ROOT / "IaC" / "ec2" / "userdata.sh"
EC2 = ROOT / "IaC" / "ec2" / "ec2.tf"
EC2_VARS = ROOT / "IaC" / "ec2" / "var.tf"
ROOT_MAIN = ROOT / "IaC" / "main.tf"
UPLOADS = ROOT / "IaC" / "uploads.tf"


class UploadsStorageTests(unittest.TestCase):
    def test_ctfd_stores_uploads_in_s3_through_the_instance_role(self):
        user_data = USER_DATA.read_text()
        self.assertIn('"UPLOAD_PROVIDER": "s3"', user_data)
        self.assertIn('"AWS_S3_BUCKET": "${UPLOAD_BUCKET_NAME}"', user_data)
        self.assertIn('"AWS_S3_REGION": "${REGION}"', user_data)
        self.assertNotIn('"UPLOAD_FOLDER":', user_data)
        self.assertIn('stale_keys = {"UPLOAD_FOLDER"}', user_data)
        self.assertNotIn("AWS_ACCESS_KEY_ID", user_data)

    def test_instance_role_can_only_touch_the_upload_bucket(self):
        ec2 = EC2.read_text()
        self.assertRegex(ec2, r'Action\s*=\s*"s3:ListBucket"\s*\n\s*Resource\s*=\s*var\.upload_bucket_arn')
        self.assertRegex(ec2, r'"s3:DeleteObject"\s*\n\s*\]\s*\n\s*Resource\s*=\s*"\$\{var\.upload_bucket_arn\}/\*"')
        self.assertNotRegex(ec2, r'"s3:\*"')
        self.assertRegex(ec2, r"UPLOAD_BUCKET_NAME\s*=\s*var\.upload_bucket_name")
        self.assertIn('variable "upload_bucket_name"', EC2_VARS.read_text())
        self.assertIn('variable "upload_bucket_arn"', EC2_VARS.read_text())

    def test_upload_bucket_is_private_encrypted_and_deployment_scoped(self):
        uploads = UPLOADS.read_text()
        self.assertRegex(uploads, r"bucket\s*=\s*local\.upload_bucket_name")
        self.assertRegex(uploads, r'force_destroy\s*=\s*var\.deployment_mode == "ephemeral"')
        for setting in ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"):
            self.assertRegex(uploads, rf"{setting}\s*=\s*true")
        self.assertIn('sse_algorithm = "AES256"', uploads)
        main = ROOT_MAIN.read_text()
        self.assertRegex(main, r"upload_bucket_name\s*=\s*aws_s3_bucket\.uploads\.bucket")
        self.assertRegex(main, r"upload_bucket_arn\s*=\s*aws_s3_bucket\.uploads\.arn")


if __name__ == "__main__":
    unittest.main()
