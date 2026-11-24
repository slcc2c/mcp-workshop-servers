#!/bin/bash
# Add API keys to AI vault

echo "🔑 Adding API Keys to AI Vault"
echo "=============================="
echo

# Function to add an API key
add_api_key() {
    local title=$1
    local field_name=$2
    local description=$3
    local example=$4
    
    echo "📝 $title"
    echo "   $description"
    echo "   Example: $example"
    echo
    
    # Check if already exists
    if op item get "$title" --vault=AI &>/dev/null; then
        echo "   ✅ Already exists in AI vault"
        read -p "   Update it? (y/n): " update_choice
        if [[ "$update_choice" != "y" ]]; then
            return
        fi
        # Delete existing to replace
        op item delete "$title" --vault=AI &>/dev/null
    fi
    
    read -p "   Enter your $title (or press Enter to skip): " api_key
    
    if [ ! -z "$api_key" ]; then
        # Create in 1Password using notesPlain field (matching your pattern)
        if op item create --vault=AI --title="$title" --category=password \
            "notesPlain[text]=$api_key" \
            "additional_notes[text]=$description" &>/dev/null; then
            echo "   ✅ Added $title to AI vault"
        else
            echo "   ❌ Failed to add $title"
        fi
    else
        echo "   ⏭️  Skipped"
    fi
    echo
}

# GitHub Personal Access Token
add_api_key "GitHub Token" "token" \
    "Personal Access Token for GitHub API access" \
    "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# OpenAI API Key
add_api_key "OpenAI API Key" "api_key" \
    "API key for OpenAI/ChatGPT access" \
    "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Anthropic API Key
add_api_key "Anthropic API Key" "api_key" \
    "API key for Claude/Anthropic access" \
    "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Optional: Additional API keys
echo "🔧 Optional API Keys:"
echo "===================="
echo

read -p "Add HuggingFace token? (y/n): " add_hf
if [[ "$add_hf" == "y" ]]; then
    add_api_key "HuggingFace Token" "token" \
        "Access token for HuggingFace models" \
        "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
fi

read -p "Add Docker Hub token? (y/n): " add_docker
if [[ "$add_docker" == "y" ]]; then
    add_api_key "Docker Hub Token" "token" \
        "Access token for Docker Hub" \
        "dckr_pat_xxxxxxxxxxxxxxxxxxxxxx"
fi

# Update .env with new references
echo
echo "📝 Updating .env with API key references..."
echo

# Check if these are already in .env, if not add them
if ! grep -q "GITHUB_TOKEN=" .env; then
    echo "" >> .env
    echo "# API Keys from AI vault" >> .env
    echo "GITHUB_TOKEN=1password:AI/GitHub Token:notesPlain" >> .env
    echo "✅ Added GITHUB_TOKEN to .env"
fi

if ! grep -q "OPENAI_API_KEY=" .env; then
    echo "OPENAI_API_KEY=1password:AI/OpenAI API Key:notesPlain" >> .env
    echo "✅ Added OPENAI_API_KEY to .env"
fi

if ! grep -q "ANTHROPIC_API_KEY=" .env; then
    echo "ANTHROPIC_API_KEY=1password:AI/Anthropic API Key:notesPlain" >> .env
    echo "✅ Added ANTHROPIC_API_KEY to .env"
fi

# Show summary
echo
echo "✅ Setup Complete!"
echo "=================="
echo
echo "Your AI vault now contains:"
op item list --vault=AI --format=json | jq -r '.[] | "  - " + .title'

echo
echo "🧪 Test your API keys:"
echo "  node test-vault-integration.js"
echo
echo "🚀 Use with MCP servers:"
echo "  npm run mcp:start"