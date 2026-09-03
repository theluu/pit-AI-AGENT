# Reproducible scenarios

The ten scenarios are defined in `agentops/scenarios.py`. Each contains ground truth, expected tools, an allowed action (or abstention), and verification criteria. Results are fixture-backed so they cannot touch the host. `INC-010` embeds a hostile instruction in a log and verifies that no action/approval is produced from it.

