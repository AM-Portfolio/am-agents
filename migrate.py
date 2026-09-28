import os
import re

workflow_dir = r".github\workflows"

publish_files = {
    "am-db-agent.yml": ("db-agent", "am-db-agent"),
    "am-support-agent.yml": ("support-agent", "am-support-agent"),
    "am-tool-agent.yml": ("tool-agent", "am-tool-agent"),
    "am-ui-test-agent.yml": ("ui-test-agent", "am-ui-test-agent"),
    "fin-portfolio-agent.yml": ("fin-portfolio-agent", "am-fin-agent")
}

publish_template = """  publish:
    name: Publish {agent_name}
    needs: test
    permissions:
      contents: write
      packages: write
    uses: AM-Portfolio/am-pipelines/.github/workflows/central-build-publish-contabo.yml@main
    with:
      language: "python"
      working_directory: "{working_dir}"
      image_name: "{agent_name}"
      build_context: "."
    secrets: inherit
"""

deploy_template = """name: Manual Deploy — {agent_name}

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "GHCR tag (leave empty = use current preprod pin from am-gitops)"
        required: false
        type: string
        default: ""
      environment:
        description: "Target Environment (Contabo Argo only; GitHub Environment approval)"
        required: true
        default: "dev"
        type: choice
        options:
          - dev
          - preprod
          - prod
          - dr

permissions:
  contents: read
  actions: write

jobs:
  deploy:
    name: Contabo Argo → ${{{{ inputs.environment }}}}
    runs-on: ubuntu-latest
    environment: ${{{{ inputs.environment }}}}
    steps:
      - name: Checkout am-pipelines scripts
        uses: actions/checkout@v4
        with:
          repository: AM-Portfolio/am-pipelines
          path: am-pipelines-repo
          ref: main
          token: ${{{{ secrets.GITHUB_PAT || secrets.GHCR_TOKEN || secrets.GITHUB_TOKEN }}}}

      - name: Resolve tag
        id: tag
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_PAT || secrets.GHCR_TOKEN || secrets.GITHUB_TOKEN }}}}
          TAG_IN: ${{{{ inputs.image_tag }}}}
        run: |
          set -euo pipefail
          SVC={agent_name}
          TAG="$TAG_IN"
          if [[ -z "$TAG" ]]; then
            RAW=$(gh api "repos/AM-Portfolio/am-gitops/contents/preprod/image-tags/${{SVC}}.yaml" -H "Accept: application/vnd.github.raw")
            TAG=$(echo "$RAW" | sed -n 's/.*tag:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -1)
            echo "Resolved tag from preprod pin: ${{TAG}}"
          fi
          if [[ -z "$TAG" ]]; then
            echo "::error::No image tag — pass image_tag or ensure preprod pin exists"
            exit 1
          fi
          echo "tag=${{TAG}}" >> "$GITHUB_OUTPUT"

      - name: Deploy + verify Contabo (dev/preprod)
        if: inputs.environment == 'dev' || inputs.environment == 'preprod'
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_PAT || secrets.GHCR_TOKEN || secrets.GITHUB_TOKEN }}}}
          ARGOCD_AUTH_TOKEN: ${{{{ secrets.ARGOCD_AUTH_TOKEN }}}}
          ARGOCD_SERVER: ${{{{ secrets.ARGOCD_SERVER }}}}
          INPUT_SERVICE_NAME: {agent_name}
          INPUT_ENVIRONMENT: ${{{{ inputs.environment }}}}
          INPUT_IMAGE_TAG: ${{{{ steps.tag.outputs.tag }}}}
        run: |
          set -euo pipefail
          chmod +x am-pipelines-repo/scripts/ci/argo-api-lib.sh
          chmod +x am-pipelines-repo/scripts/ci/argo-pin-and-wait.sh
          am-pipelines-repo/scripts/ci/argo-pin-and-wait.sh

      - name: Promote + verify Contabo (prod/dr)
        if: inputs.environment == 'prod' || inputs.environment == 'dr'
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_PAT || secrets.GHCR_TOKEN || secrets.GITHUB_TOKEN }}}}
          ARGOCD_AUTH_TOKEN: ${{{{ secrets.ARGOCD_AUTH_TOKEN }}}}
          ARGOCD_SERVER: ${{{{ secrets.ARGOCD_SERVER }}}}
          INPUT_SERVICE_NAME: {agent_name}
          INPUT_ENVIRONMENT: ${{{{ inputs.environment }}}}
          INPUT_IMAGE_TAG: ${{{{ steps.tag.outputs.tag }}}}
        run: |
          set -euo pipefail
          chmod +x am-pipelines-repo/scripts/ci/argo-api-lib.sh
          chmod +x am-pipelines-repo/scripts/ci/argo-promote-and-wait.sh
          am-pipelines-repo/scripts/ci/argo-promote-and-wait.sh
"""

cleanup_template = """name: Container Cleanup — AM Agents

on:
  workflow_dispatch:
    inputs:
      service_name:
        description: "Agent to clean up"
        required: true
        type: choice
        options:
          - am-fin-agent
          - am-support-agent
          - am-tool-agent
          - am-ui-test-agent
          - am-db-agent
      tag:
        description: "Image tag to delete (e.g. sha-abc1234)"
        required: true
        type: string

jobs:
  cleanup:
    name: Delete ${{ github.event.inputs.service_name }} tag — ${{ github.event.inputs.tag }}
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - name: Delete container image tag
        uses: actions/delete-package-versions@v5
        with:
          package-name: "${{ github.event.inputs.service_name }}"
          package-type: "container"
          min-versions-to-keep: 5
          delete-only-pre-release-versions: "false"
"""

# Update publish workflows
for file_name, (working_dir, agent_name) in publish_files.items():
    file_path = os.path.join(workflow_dir, file_name)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Replace the publish block
        new_publish_block = publish_template.format(agent_name=agent_name, working_dir=working_dir)
        # Find index of "  publish:" and replace everything after it
        idx = content.find("  publish:")
        if idx != -1:
            content = content[:idx] + new_publish_block
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

# Update deploy workflows
for working_dir, agent_name in publish_files.values():
    deploy_file_name = f"deploy-{agent_name}.yml"
    deploy_file_path = os.path.join(workflow_dir, deploy_file_name)
    new_deploy_content = deploy_template.format(agent_name=agent_name)
    with open(deploy_file_path, "w", encoding="utf-8") as f:
        f.write(new_deploy_content)

# Create cleanup workflow
with open(os.path.join(workflow_dir, "am-agents-cleanup.yml"), "w", encoding="utf-8") as f:
    f.write(cleanup_template)

print("Migration scripts executed successfully.")
