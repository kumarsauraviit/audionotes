#!/usr/bin/env bash
# Bootstrap a Debian/Ubuntu Compute Engine VM to run the Audio Notes backend.
# Idempotent: safe to re-run. Run as root (the deploy script does `sudo bash`).
set -euo pipefail

APP_DIR="/opt/audionotes"
TARGET_USER="${SUDO_USER:-${USER:-root}}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"
[[ -n "${TARGET_HOME:-}" ]] || TARGET_HOME="/root"

echo ">> Target user: ${TARGET_USER} (${TARGET_HOME})"

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker Engine + Compose plugin"
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings

  . /etc/os-release
  case "${ID}" in
    debian|ubuntu) DOCKER_DISTRO="${ID}" ;;
    *)
      echo "Unsupported distro '${ID}'; expected Debian or Ubuntu." >&2
      exit 1
      ;;
  esac

  curl -fsSL "https://download.docker.com/linux/${DOCKER_DISTRO}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  ARCH="$(dpkg --print-architecture)"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${DOCKER_DISTRO} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo ">> Docker already installed: $(docker --version)"
fi

if id "$TARGET_USER" >/dev/null 2>&1 && ! id -nG "$TARGET_USER" | grep -qw docker; then
  usermod -aG docker "$TARGET_USER" || true
  echo ">> Added ${TARGET_USER} to the docker group (re-login to use docker without sudo)."
fi

install -d -o "$TARGET_USER" -g "$TARGET_USER" "$APP_DIR"
echo ">> Ready. Deploy files belong in ${APP_DIR}."
