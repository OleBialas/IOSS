#!/bin/bash
# Boot script of a sandbox instance. Cloud-init runs it once, as root.
# The launcher replaces the double-underscore placeholders with shell-quoted
# values.
#
# No `set -x`: the console log must not show the password or the bundle URL.
set -euo pipefail
exec > >(tee -a /var/log/ioss-setup.log) 2>&1
trap 'echo "IOSS: setup failed at line $LINENO (exit $?)"' ERR

# Safety net: the instance ends after its lifetime, even when the launcher
# does not clean up. The launch template turns a shutdown into a termination.
shutdown -h +__MINUTES__

export HOME=/root DEBIAN_FRONTEND=noninteractive

echo "IOSS: installing Docker"
# On the first boot, unattended-upgrades often holds the apt lock.
APT=(apt-get -q -o DPkg::Lock::Timeout=600)
"${APT[@]}" update
"${APT[@]}" install -y docker.io docker-compose-v2 git python3 curl
systemctl enable --now docker

imds() {
  local token
  token=$(curl -sf -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  curl -sf -H "X-aws-ec2-metadata-token: $token" \
    "http://169.254.169.254/latest/meta-data/$1"
}
# Inside the VPC this name resolves to the private IP, so CI jobs reach
# Forgejo at ROOT_URL too.
HOST=$(imds public-hostname)

echo "IOSS: downloading the sandbox bundle"
mkdir -p /opt/ioss
if ! curl -sSL --fail-with-body --retry 3 -o /tmp/ioss-bundle.zip __BUNDLE_URL__; then
  # S3 explains the error in the response body.
  cat /tmp/ioss-bundle.zip || true
  echo
  echo "IOSS: setup failed: cannot download the sandbox bundle"
  exit 1
fi
python3 -m zipfile -e /tmp/ioss-bundle.zip /opt/ioss
rm /tmp/ioss-bundle.zip

echo "IOSS: starting Forgejo at http://$HOST:3000/"
cd /opt/ioss/sandbox
export FORGEJO_ROOT_URL="http://$HOST:3000/" FORGEJO_BIND=0.0.0.0
docker compose up -d

echo "IOSS: populating the sandbox"
IOSS_NEWCOMER_PASSWORD=__NEWCOMER_PASSWORD__ python3 setup.py
echo "IOSS: ready"
