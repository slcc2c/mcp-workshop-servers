#!/usr/bin/env python3
"""
Quick test: Run 2 turns to verify setup before going overnight.
"""
import asyncio
import subprocess

async def test_claude():
    print("🟣 Testing Claude Code --print mode...")
    proc = await asyncio.create_subprocess_exec(
        "claude", "--print", "Say 'Claude OK' and nothing else.",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    result = stdout.decode().strip()
    print(f"   Response: {result[:100]}")
    return "OK" in result or "Claude" in result

async def test_codex():
    print("🟢 Testing Codex exec mode...")
    proc = await asyncio.create_subprocess_exec(
        "codex", "exec", 
        "--full-auto",
        "--skip-git-repo-check",  # Allow running outside git repos
        "Say 'Codex OK' and nothing else.",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    result = stdout.decode().strip()
    err = stderr.decode().strip()
    print(f"   Response: {result[:100]}")
    if err:
        print(f"   Stderr: {err[:100]}")
    return len(result) > 0 or "OK" in result

async def main():
    print("━" * 50)
    print("OVERNIGHT AGENT SETUP TEST")
    print("━" * 50)
    
    claude_ok = await test_claude()
    codex_ok = await test_codex()
    
    print("\n━" * 50)
    print(f"Claude Code: {'✅ Ready' if claude_ok else '❌ Failed'}")
    print(f"Codex:       {'✅ Ready' if codex_ok else '❌ Failed (check flags)'}")
    print("━" * 50)
    
    if claude_ok and codex_ok:
        print("\n🚀 Ready for overnight run!")
        print("   ./overnight.sh /path/to/repo 8")
    else:
        print("\n⚠️  Fix issues above before running overnight.")
        print("\nTroubleshooting:")
        print("   Claude: claude --print 'test prompt'")
        print("   Codex:  codex exec --full-auto 'test prompt'")
        print("\nCheck API keys are set in environment.")
        print("Codex needs: OPENAI_API_KEY")
        print("Claude needs: ANTHROPIC_API_KEY (or be logged in)")


if __name__ == "__main__":
    asyncio.run(main())
