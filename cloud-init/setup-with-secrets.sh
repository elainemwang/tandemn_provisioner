#!/bin/bash
set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting VLLM setup script with AWS Secrets Manager"

# Verify NVIDIA is working (should already be installed in custom AMI)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Verifying NVIDIA drivers"
nvidia-smi

# Install AWS CLI
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing AWS CLI"
apt-get update
apt-get install -y unzip curl
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
./aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
rm -rf awscliv2.zip aws

# Install UV package manager
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing UV"
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup VLLM
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cloning VLLM repository"
git clone https://github.com/Tandemn-Labs/tandemn-vllm /opt/tandemn-vllm

# Create .env file from AWS Secrets Manager
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating .env file from AWS Secrets Manager"
cd /opt/tandemn-vllm

# Fetch secrets from AWS Secrets Manager
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fetching secrets from AWS Secrets Manager"
SECRETS=$(aws secretsmanager get-secret-value --secret-id tandemn-vllm-env --query SecretString --output text)

# Create .env file with secrets and dynamic SERVER_HOST
cat > .env << EOF
# Server settings
SERVER_HOST=${server_host}
SERVER_PORT=8000

# Environment variables from AWS Secrets Manager
$SECRETS
EOF
echo "Environment file created from AWS Secrets Manager"

# Setup Python environment and start machine runner
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting up Python environment"
cd /opt/tandemn-vllm
export PATH="/root/.local/bin:$PATH"
uv venv -p 3.12
. .venv/bin/activate
uv pip install -r requirements.peer.txt
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting machine runner"
nohup .venv/bin/python -m src.machine_runner > /var/log/machine_runner.log 2>&1 &
echo $! > /var/run/machine_runner.pid

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setup completed - machine runner started"
