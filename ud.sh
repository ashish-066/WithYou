#!/bin/bash
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ssm-user || true
