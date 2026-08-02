from __future__ import annotations

from unittest import TestCase

from stock_opportunity_agent.llm import (
    ModelClientSettings,
    RegisteredModel,
    get_model,
    model_catalog,
)
from stock_opportunity_agent.models import ValidationError


class LLMModelRegistryTests(TestCase):
    def test_catalog_auto_discovers_role_aware_model_aliases(self) -> None:
        catalog = {item.alias: item for item in model_catalog()}
        self.assertIn("codex-reviewed-file", catalog)
        self.assertIn("openrouter-fusion", catalog)
        self.assertIn("kimi-k3-together", catalog)
        self.assertIn("gpt-4.1-openai", catalog)
        self.assertIn("deepseek-v4-flash", catalog)
        self.assertEqual(
            catalog["deepseek-v4-flash"].roles,
            ("evolution", "judge"),
        )
        self.assertFalse(catalog["deepseek-v4-flash"].web_tools_allowed)
        self.assertTrue(
            {"codex-reviewed-file", "openrouter-fusion"}.issubset(
                {item.alias for item in model_catalog(role="evolution")}
            )
        )
        self.assertIn(
            "local-heuristic",
            {item.alias for item in model_catalog(role="judge")},
        )

    def test_role_mismatch_and_unknown_alias_fail_with_available_models(self) -> None:
        with self.assertRaisesRegex(ValidationError, "does not support role"):
            get_model("openrouter-fusion", role="judge")
        with self.assertRaisesRegex(ValidationError, "available"):
            get_model("not-registered", role="evolution")

    def test_preview_client_construction_never_requires_real_credentials(self) -> None:
        for alias in (
            "openrouter-fusion",
            "kimi-k3-together",
            "gpt-4.1-openai",
            "deepseek-v4-flash",
        ):
            registration = get_model(alias)
            client = registration.create_client(
                ModelClientSettings(preview_only=True, environ={})
            )
            self.assertEqual(client.model, registration.model)
            self.assertTrue(client.api_key.startswith("preview-"))

    def test_generic_external_proposer_requires_positive_registered_prices(self) -> None:
        with self.assertRaisesRegex(ValidationError, "token prices must be positive"):
            RegisteredModel(
                alias="invalid-plain-proposer",
                provider="fake",
                model="fake-model",
                roles=("evolution",),
                api_key_env_var="FAKE_API_KEY",
                description="fixture",
                client_factory=lambda _settings: None,
                proposal_profile="plain_json",
                default_input_cost_per_million_tokens=0.0,
                default_output_cost_per_million_tokens=1.0,
            )
