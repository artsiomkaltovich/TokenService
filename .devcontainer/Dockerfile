FROM mcr.microsoft.com/devcontainers/base:bookworm

# System dependencies (including nodejs for IDE remote agent support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    libssl-dev \
    pkg-config \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

USER vscode
ENV HOME="/home/vscode"
ENV PATH="/home/vscode/.local/share/mise/shims:/home/vscode/.local/bin:$PATH"
ENV UV_CACHE_DIR="/workspaces/.uv_cache"

# Install mise version manager
RUN curl https://mise.jdx.dev/install.sh | sh

# Install CLI LLM Agent
# RUN curl -fsSL https://antigravity.google/cli/install.sh | bash
# RUN curl -fsSL https://gh.io/copilot-install | bash
# RUN curl -fsSL https://chatgpt.com/codex/install.sh | sh
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# Trust workspace config and create initial lock file
COPY --chown=vscode:vscode mise.toml /home/vscode/mise.toml
RUN cd /home/vscode && mise trust && mise install --yes

# Shell hooks for interactive terminals
RUN echo 'eval "$(/home/vscode/.local/bin/mise activate bash)"' >> /home/vscode/.bashrc && \
    echo 'eval "$(/home/vscode/.local/bin/mise activate zsh)"' >> /home/vscode/.zshrc
