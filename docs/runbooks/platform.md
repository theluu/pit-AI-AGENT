# Platform Recovery Runbook

## Redis and worker recovery

Confirm Redis PING, port reachability, workload state and queue depth. Restart only the failed dependency or worker. Verification requires a successful health check and a decreasing queue depth.

## Disk pressure

Confirm filesystem utilization and the largest bounded demo path. Rotate demo logs through the typed action; deletion, arbitrary paths and volumes are forbidden.

## Deployment rollback

Correlate the error increase with deployment history. Rollback is R3, must name the exact previous version, show expected impact, and receive the literal confirmation `CONFIRM R3`.
