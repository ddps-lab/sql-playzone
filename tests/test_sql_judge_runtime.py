import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCAL_COMPOSE = ROOT / "platform" / "docker-compose.yml"
PRODUCTION_COMPOSE = ROOT / "platform" / "docker-compose.production.yml"
USER_DATA = ROOT / "IaC" / "ec2" / "userdata.sh"
JUDGE_SOURCE = (
    ROOT
    / "platform"
    / "CTFd"
    / "plugins"
    / "sql_challenges"
    / "sql_judge_server.go"
)


def service_block(compose: str, service: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|^networks:)", compose)
    if not match:
        raise AssertionError(f"service {service} not found")
    return match.group(1)


class SQLJudgeRuntimeTests(unittest.TestCase):
    def test_mysql_is_pinned_private_and_resource_limited(self):
        for path in (LOCAL_COMPOSE, PRODUCTION_COMPOSE):
            compose = path.read_text()
            mysql = service_block(compose, "mysql-judge")
            self.assertRegex(mysql, r"image: mysql:8\.4@sha256:[0-9a-f]{64}")
            self.assertNotIn("ports:", mysql)
            self.assertIn(".env.judge", mysql)
            self.assertIn("judge-db", mysql)
            self.assertIn("--disable-log-bin", mysql)
            self.assertIn("--event-scheduler=DISABLED", mysql)
            self.assertIn("--lower-case-table-names=1", mysql)
            self.assertIn("--collation-server=utf8mb4_0900_ai_ci", mysql)
            self.assertIn("--innodb-flush-log-at-trx-commit=2", mysql)
            self.assertIn("--max-connections=64", mysql)
            self.assertIn("--performance-schema=OFF", mysql)
            self.assertIn("--skip-name-resolve", mysql)
            self.assertIn("mem_limit: 768m", mysql)
            self.assertIn('127.0.0.1", "--silent"', mysql)

    def test_ctfd_cannot_receive_mysql_secret_or_reach_mysql_network(self):
        for path in (LOCAL_COMPOSE, PRODUCTION_COMPOSE):
            compose = path.read_text()
            ctfd = service_block(compose, "ctfd")
            judge = service_block(compose, "sql-judge")
            self.assertNotIn(".env.judge", ctfd)
            self.assertNotIn("judge-db", ctfd)
            self.assertIn(".env.judge", judge)
            self.assertIn("internal", judge)
            self.assertIn("judge-db", judge)

    def test_ctfd_waits_for_a_healthy_judge(self):
        for path in (LOCAL_COMPOSE, PRODUCTION_COMPOSE):
            compose = path.read_text()
            ctfd = service_block(compose, "ctfd")
            judge = service_block(compose, "sql-judge")
            self.assertRegex(ctfd, r"sql-judge:\n\s+condition: service_healthy")
            self.assertIn("healthcheck:", judge)
            self.assertIn("http://127.0.0.1:8080/health", judge)

    def test_boot_generates_a_stable_instance_local_mysql_password(self):
        user_data = USER_DATA.read_text()
        self.assertIn('judge_env_path = Path(".env.judge")', user_data)
        self.assertIn('existing_judge_values.get("MYSQL_ROOT_PASSWORD") or secrets.token_hex(32)', user_data)
        self.assertIn("chmod 600 .env .env.judge", user_data)

    def test_go_server_uses_per_execution_accounts_without_wildcard_grants(self):
        source = JUDGE_SOURCE.read_text()
        self.assertIn('temporaryDatabasePrefix = "ctfd_tmp_"', source)
        self.assertIn('temporaryUserPrefix     = "ct_"', source)
        self.assertIn("CREATE USER ", source)
        self.assertIn("DROP USER IF EXISTS ", source)
        self.assertIn("KILL CONNECTION", source)
        self.assertIn("GRANT SELECT, SHOW VIEW ON ", source)
        self.assertIn('"MAX_EXECUTION_TIME",', source)
        self.assertNotIn("ctfd\\_tmp\\_%", source)
        self.assertNotIn("go-mysql-server", source)
        self.assertIn("MultiStatements = false", source)
        self.assertIn("ParseTime = false", source)


if __name__ == "__main__":
    unittest.main()
