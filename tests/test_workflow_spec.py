from src.orchestrator.workflow_spec import MARKET_COVERAGE, PHASE_ORDER, workflow_manifest


def test_workflow_manifest_exposes_seven_phases():
    manifest = workflow_manifest()
    assert len(PHASE_ORDER) == 7
    assert manifest["phases"][-1] == "publish"


def test_crypto_is_not_advertised_as_live_before_provider_registry_support():
    assert MARKET_COVERAGE["crypto"]["status"] == "planned"
