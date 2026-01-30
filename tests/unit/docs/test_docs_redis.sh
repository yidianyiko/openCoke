#!/bin/bash
set -euo pipefail

rg -n "redis" doc/ops/devops_new_instance.md doc/ops/devops_start_instance.md
