FROM python:3.11-slim

# The vault daemon uses git internally to check status and commits, so it must be installed.
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the AgentDrive source code
COPY . .

# Install the CLI package globally within the container
RUN pip install --no-cache-dir .

# Set the vault CLI as the default entrypoint
ENTRYPOINT ["vault"]
CMD ["--help"]
