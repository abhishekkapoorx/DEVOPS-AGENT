import json
from pathlib import Path


def test_monitoring_manifests_cover_alertable_scenarios_and_read_only_rbac():
    rules = Path("deploy/monitoring/prometheus-rules.yaml").read_text(encoding="utf-8")
    rbac = Path("deploy/monitoring/rbac-readonly.yaml").read_text(encoding="utf-8")

    for alert_name in (
        "KubePodCrashLooping",
        "KubeContainerOOMKilled",
        "ServiceNoEndpoints",
        "KubePodNotReady",
        "KubeDeploymentReplicasMismatch",
    ):
        assert f"alert: {alert_name}" in rules
    fixture_names = {
        json.loads(path.read_text(encoding="utf-8"))["alerts"][0]["labels"]["alertname"]
        for path in Path("incident-investigation-lab/scenarios").glob("*/alert_fixture.json")
    }
    for name in fixture_names - {"HighLatency"}:
        assert f"alert: {name}" in rules
    assert 'verbs: ["get", "list", "watch"]' in rbac
    assert "secrets" not in rbac
    assert "delete" not in rbac
    assert "patch" not in rbac


def test_monitoring_configuration_uses_file_based_webhook_secret():
    values = Path("deploy/monitoring/values.yaml").read_text(encoding="utf-8")

    assert "credentials_file:" in values
    assert "incident-webhook-token/token" in values
    assert "WEBHOOK_TOKEN" not in values
