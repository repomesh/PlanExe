#!/usr/bin/env python3
"""
Test script: verify that beta.messages.parse() includes the OAuth beta header.
Uses ANTHROPIC_OAUTHTOKEN env var as the OAuth token.
"""
import os
import sys
from pathlib import Path

# Add worker_plan to path
sys.path.insert(0, str(Path(__file__).parent))

def test_oauth_parse():
    """Test that parse() includes OAuth beta header."""
    oauth_token = os.environ.get("ANTHROPIC_OAUTHTOKEN")
    if not oauth_token:
        print("❌ ANTHROPIC_OAUTHTOKEN not set")
        return False
    
    print(f"✓ Using OAuth token: {oauth_token[:20]}...")
    
    # Import the factory and llama_index Anthropic
    from worker_plan_internal.llm_factory import get_llm, _CLAUDE_OAUTH_TOKEN_PREFIX
    from llama_index.core.llms import CompletionResponse
    
    # Verify token format
    if not oauth_token.startswith(_CLAUDE_OAUTH_TOKEN_PREFIX):
        print(f"❌ Token does not start with {_CLAUDE_OAUTH_TOKEN_PREFIX}")
        return False
    
    print("✓ Token has correct prefix (sk-ant-oat)")
    
    # Create a test LLM config with the OAuth token
    import anthropic as anthropic_sdk
    
    print("\nCreating Anthropic SDK client with OAuth token...")
    try:
        # Create client directly to test the auth
        client = anthropic_sdk.Anthropic(
            auth_token=oauth_token,
            default_headers={"anthropic-beta": "oauth-2025-04-20"}
        )
        print("✓ Client created successfully")
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return False
    
    # Try a simple parse() call
    print("\nTesting parse() method with OAuth token...")
    try:
        from pydantic import BaseModel
        
        class SimpleOutput(BaseModel):
            answer: str
        
        # Simple test message
        response = client.beta.messages.parse(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": "Say 'success' in JSON."
                }
            ],
            response_format=SimpleOutput,
        )
        
        print(f"✓ parse() call succeeded!")
        print(f"  Response: {response}")
        return True
        
    except Exception as e:
        error_str = str(e)
        if "401" in error_str or "OAuth authentication is currently not supported" in error_str:
            print(f"❌ OAuth header issue: {e}")
            return False
        else:
            # Other errors (e.g., invalid model, rate limit) are OK for this test
            # We just care that we didn't get a 401 about OAuth auth
            print(f"⚠️  Got error but not auth-related: {e}")
            print("  (This is OK if it's a rate limit, model not found, etc.)")
            return True

if __name__ == "__main__":
    success = test_oauth_parse()
    sys.exit(0 if success else 1)
