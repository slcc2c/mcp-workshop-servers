#!/usr/bin/env python3
"""
Overnight multi-agent repo analysis: Claude Code ↔ Codex
Both agents save observations to memory MCP as they go.

Usage:
    python overnight-agents.py --repo /path/to/repo --hours 8
    
    # Or run in background:
    nohup python overnight-agents.py --repo ~/repos/mcp-server --hours 8 &
"""

import subprocess
import json
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_REPO = "/Users/spencer/repos/mcp-server"
MAX_TURNS = 200
TURN_DELAY_SECONDS = 10  # Brief pause between agent turns
CHECKPOINT_EVERY = 5    # Save summary checkpoint every N turns

# Memory MCP integration - Claude Code already has this configured
# We instruct Claude to save observations as part of its prompts


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════
def get_system_context(repo_path: str, turn: int, agent_name: str) -> str:
    return f"""You are {agent_name}, analyzing the repository at {repo_path}.
Turn: {turn}

CRITICAL INSTRUCTIONS:
1. You are in a multi-agent discussion with another AI. Your partner will respond after you.
2. Be specific - reference actual files, functions, line numbers.
3. After your analysis, ALWAYS use memory MCP to save your key observations:
   - Use create_entities or add_observations to persist findings
   - Entity naming: "overnight_analysis_turn_{turn}_{agent_name.lower()}"
   - Include: file paths, issues found, suggestions, questions for partner
4. End with a specific question or area for your partner to explore.

Focus areas (rotate through these):
- Architecture & design patterns
- Potential bugs or edge cases  
- Performance optimizations
- Security considerations
- Code quality & maintainability
- Test coverage gaps"""


def get_claude_initial_prompt(repo_path: str) -> str:
    return f"""{get_system_context(repo_path, 1, "Claude")}

Start by exploring the repo structure. Identify:
1. The overall architecture
2. The 3 most interesting/concerning areas to discuss
3. Any immediate red flags

Save your initial observations to memory MCP, then pose a question for Codex."""


def get_response_prompt(repo_path: str, turn: int, agent_name: str, 
                        partner_name: str, partner_response: str) -> str:
    return f"""{get_system_context(repo_path, turn, agent_name)}

{partner_name}'s previous analysis:
---
{partner_response[:6000]}
---

Respond to {partner_name}'s observations:
1. Agree/disagree with specific points (cite evidence)
2. Add your own analysis on areas they mentioned
3. Explore something new they may have missed
4. Save key findings to memory MCP
5. End with a focused question for the next turn"""


def get_checkpoint_prompt(repo_path: str, turn: int, recent_history: list) -> str:
    history_summary = "\n\n".join([
        f"Turn {h['turn']} ({h['agent']}): {h['content'][:500]}..."
        for h in recent_history[-6:]
    ])
    return f"""Create a checkpoint summary of the overnight analysis so far.

Repository: {repo_path}
Current turn: {turn}

Recent discussion:
{history_summary}

Synthesize into a structured summary and save to memory MCP as entity "overnight_checkpoint_turn_{turn}":
- Key findings (bugs, issues, improvements)
- Open questions still being explored
- Consensus points between agents
- Disagreements or areas needing more investigation"""


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT RUNNERS  
# ═══════════════════════════════════════════════════════════════════════════════
async def run_claude(prompt: str, repo_path: str, timeout: int = 300) -> str:
    """Run Claude Code in headless/print mode."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",                         # Non-interactive, stdout output
            "--dangerously-skip-permissions",  # Full autonomy for overnight
            "--output-format", "text",         # Plain text output
            prompt,                             # Prompt is positional arg
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), 
            timeout=timeout
        )
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        proc.kill()
        return "[Claude timed out after {timeout}s]"
    except Exception as e:
        return f"[Claude error: {e}]"


async def run_codex(prompt: str, repo_path: str, timeout: int = 300) -> str:
    """Run Codex CLI in non-interactive exec mode."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "exec",                                        # Non-interactive subcommand
            "--full-auto",                                 # Low-friction automatic execution  
            "-C", repo_path,                               # Explicit working directory
            prompt,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        proc.kill()
        return f"[Codex timed out after {timeout}s]"
    except Exception as e:
        return f"[Codex error: {e}]"


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════
class ConversationLogger:
    def __init__(self, repo_path: str):
        self.log_dir = Path(repo_path) / ".overnight-analysis"
        self.log_dir.mkdir(exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"session_{self.session_id}.jsonl"
        self.transcript_file = self.log_dir / f"transcript_{self.session_id}.md"
        
    def log_turn(self, turn: int, agent: str, prompt: str, response: str):
        # JSONL for structured data
        entry = {
            "timestamp": datetime.now().isoformat(),
            "turn": turn,
            "agent": agent,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "response": response,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        # Markdown transcript for human reading
        with open(self.transcript_file, "a") as f:
            f.write(f"\n\n---\n## Turn {turn} | {agent} | {datetime.now().strftime('%H:%M:%S')}\n\n")
            f.write(response)
    
    def log_checkpoint(self, turn: int, summary: str):
        with open(self.transcript_file, "a") as f:
            f.write(f"\n\n---\n## 📋 CHECKPOINT (Turn {turn})\n\n{summary}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATION LOOP
# ═══════════════════════════════════════════════════════════════════════════════
async def run_overnight(repo_path: str, hours: float):
    end_time = datetime.now() + timedelta(hours=hours)
    logger = ConversationLogger(repo_path)
    history = []
    turn = 0
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🌙 OVERNIGHT MULTI-AGENT ANALYSIS                               ║
╠══════════════════════════════════════════════════════════════════╣
║  Repo:     {repo_path:<50} ║
║  Duration: {hours} hours (until {end_time.strftime('%H:%M')})                              ║
║  Logs:     {logger.log_dir}                                      ║
╚══════════════════════════════════════════════════════════════════╝
""")

    # ─── Initial Claude turn ───
    turn = 1
    print(f"\n🟣 Turn {turn} | Claude Code starting analysis...")
    
    claude_prompt = get_claude_initial_prompt(repo_path)
    claude_response = await run_claude(claude_prompt, repo_path)
    
    print(f"   └─ {len(claude_response)} chars | {claude_response[:200]}...")
    logger.log_turn(turn, "Claude", claude_prompt, claude_response)
    history.append({"turn": turn, "agent": "Claude", "content": claude_response})
    
    await asyncio.sleep(TURN_DELAY_SECONDS)
    
    # ─── Main conversation loop ───
    while datetime.now() < end_time and turn < MAX_TURNS:
        turn += 1
        
        # Codex's turn
        print(f"\n🟢 Turn {turn} | Codex responding...")
        codex_prompt = get_response_prompt(
            repo_path, turn, "Codex", "Claude", claude_response
        )
        codex_response = await run_codex(codex_prompt, repo_path)
        
        print(f"   └─ {len(codex_response)} chars | {codex_response[:200]}...")
        logger.log_turn(turn, "Codex", codex_prompt, codex_response)
        history.append({"turn": turn, "agent": "Codex", "content": codex_response})
        
        await asyncio.sleep(TURN_DELAY_SECONDS)
        
        # Check for checkpoint
        if turn % CHECKPOINT_EVERY == 0:
            print(f"\n📋 Creating checkpoint at turn {turn}...")
            checkpoint_prompt = get_checkpoint_prompt(repo_path, turn, history)
            checkpoint = await run_claude(checkpoint_prompt, repo_path)
            logger.log_checkpoint(turn, checkpoint)
        
        turn += 1
        
        # Claude's turn
        print(f"\n🟣 Turn {turn} | Claude Code responding...")
        claude_prompt = get_response_prompt(
            repo_path, turn, "Claude", "Codex", codex_response
        )
        claude_response = await run_claude(claude_prompt, repo_path)
        
        print(f"   └─ {len(claude_response)} chars | {claude_response[:200]}...")
        logger.log_turn(turn, "Claude", claude_prompt, claude_response)
        history.append({"turn": turn, "agent": "Claude", "content": claude_response})
        
        await asyncio.sleep(TURN_DELAY_SECONDS)
        
        # Check for stale conversation
        if len(claude_response) < 100 or len(codex_response) < 100:
            print("\n⚠️  Responses getting thin, injecting new direction...")
            claude_prompt = f"""The conversation is getting repetitive. 
Pick a completely new file or area of the codebase that hasn't been discussed yet.
Do a deep dive and save findings to memory MCP."""
    
    # ─── Final summary ───
    print(f"\n\n🌅 Analysis complete! {turn} turns over {hours} hours")
    
    final_prompt = f"""Create a FINAL REPORT of this overnight analysis session.

Review all findings saved to memory MCP during this session (entities starting with "overnight_").

Structure the report:
1. Executive Summary (3-4 sentences)
2. Critical Issues Found (with file:line references)
3. Recommended Improvements (prioritized)
4. Security Considerations
5. Areas Needing Human Review

Save this as entity "overnight_final_report_{logger.session_id}" in memory MCP."""

    print("📝 Generating final report...")
    final_report = await run_claude(final_prompt, repo_path, timeout=600)
    logger.log_turn(turn + 1, "Final Report", final_prompt, final_report)
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  ✅ OVERNIGHT ANALYSIS COMPLETE                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Total turns:  {turn:<48} ║
║  Transcript:   {str(logger.transcript_file):<48} ║
║  Structured:   {str(logger.log_file):<48} ║
║  Memory MCP:   Check entities starting with "overnight_"         ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    return history


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run overnight multi-agent repo analysis"
    )
    parser.add_argument(
        "--repo", "-r",
        default=DEFAULT_REPO,
        help="Path to repository to analyze"
    )
    parser.add_argument(
        "--hours", "-t",
        type=float,
        default=8,
        help="Hours to run (default: 8)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test with 2 turns only"
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        MAX_TURNS = 2
        args.hours = 0.1
    
    asyncio.run(run_overnight(args.repo, args.hours))
