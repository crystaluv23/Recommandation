import json
import tempfile
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.config import AgentConfig, DataSourceConfig, load_config
from stock_opportunity_agent.models import ValidationError


class ConfigTests(TestCase):
    def test_default_config_is_valid_and_versioned(self) -> None:
        config = load_config(environ={})

        self.assertIsInstance(config, AgentConfig)
        self.assertEqual(config.config_version, "config-v0.1")
        self.assertEqual(config.universe.min_market_cap_usd, 5_000_000_000)
        self.assertEqual(config.pipeline.weekly_watchlist_size, 20)

    def test_json_config_and_environment_overrides_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "config_version": "file-config",
                        "storage": {"reports_dir": "file-reports"},
                        "pipeline": {"weekly_watchlist_size": 12},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                path,
                environ={
                    "SOA_CONFIG_VERSION": "env-config",
                    "SOA_STORAGE_ROOT_DIR": ".state-test",
                    "SOA_MASSIVE_API_KEY_ENV_VAR": "CUSTOM_MASSIVE_KEY",
                    "SOA_STOOQ_API_KEY_ENV_VAR": "CUSTOM_STOOQ_KEY",
                },
            )

        self.assertEqual(config.config_version, "env-config")
        self.assertEqual(config.storage.root_dir, ".state-test")
        self.assertEqual(config.storage.reports_dir, "file-reports")
        self.assertEqual(config.pipeline.weekly_watchlist_size, 12)
        self.assertEqual(config.data_sources.massive_api_key_env_var, "CUSTOM_MASSIVE_KEY")
        self.assertEqual(config.data_sources.stooq_api_key_env_var, "CUSTOM_STOOQ_KEY")

    def test_invalid_thresholds_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            load_config(
                environ={},
                path=_temp_config(
                    {
                        "scoring": {
                            "min_score_for_watchlist": 0.8,
                            "min_score_for_action_candidate": 0.7,
                        }
                    }
                ),
            )

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            load_config(environ={}, path=_temp_config({"brokerage": {"enabled": True}}))

    def test_public_config_does_not_include_secret_values(self) -> None:
        config = AgentConfig(
            data_sources=DataSourceConfig(
                price_source="vendor",
                fundamentals_source="vendor",
                document_source="local",
                massive_api_key_env_var="VENDOR_API_KEY",
                credential_env_vars=("VENDOR_API_KEY",),
            )
        )

        public = config.public_dict()

        self.assertIn("VENDOR_API_KEY", public["data_sources"]["credential_env_vars"])
        self.assertNotIn("secret-value", json.dumps(public))


def _temp_config(data: dict) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    with handle:
        json.dump(data, handle)
    return Path(handle.name)
