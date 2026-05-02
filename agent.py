import os
import re
import json
import httpx
import platform
from litellm import acompletion
from zb_tools import TOOLS, handle_tool_call, get_tools_prompt_description

API_BASE = "http://localhost:8000/v1"
MODEL = "openai/deepseek-chat"
os.environ["OPENAI_API_KEY"] = "sk-zerobound"

def get_system_prompt() -> str:
    system_os = platform.system()
    release = platform.release()
    
    return f"""--- IDENTITY ---
You are ZeroBound CLI, a lightweight terminal-based autonomous agent.
Current Host OS: {system_os} {release}
You MUST adapt your terminal commands and file paths for {system_os}.

--- RESPONSE MODES ---
1. **ACTION MODE**: Used to execute tools. Include <THINK> and [ACTION] blocks.
2. **REPORT MODE**: Used to communicate back to the user. Include <THINK> and [REPORT] blocks.

**CRITICAL RULE**: Do NOT combine [ACTION] and [REPORT] in the same response. If you need to use a tool, use [ACTION] and WAIT for the result. Only use [REPORT] AFTER you have seen the tool results in your history.

--- TOOL SYNTAX (STRICT JSON) ---
Invoke tools EXACTLY like this inside [ACTION]:
CALL: tool_name({{"arg": "val"}})

{get_tools_prompt_description()}

--- FORMATTING ---
Respond in plain text or simple markdown suitable for a terminal. 
Do not use complex HTML or advanced markdown features that a basic terminal cannot render.
"""

def _fix_json_string(json_str: str) -> str:
    """Safely escape raw newlines and fix backslashes without corrupting existing ones."""
    # Fix raw newlines
    fixed = json_str.replace('\n', '\\n').replace('\r', '\\r')
    
    # Simple backslash fix: Only escape backslashes that are NOT followed by a valid JSON escape char
    # We'll use a simpler approach: if a backslash is followed by something that isn't a valid escape, we escape it.
    valid_escapes = '"\\/bfnrtu'
    result = []
    i = 0
    while i < len(fixed):
        if fixed[i] == '\\':
            if i + 1 < len(fixed) and fixed[i+1] in valid_escapes:
                # Keep valid escape
                result.append(fixed[i:i+2])
                i += 2
                continue
            else:
                # Escape the naked backslash
                result.append('\\\\')
                i += 1
                continue
        result.append(fixed[i])
        i += 1
    return "".join(result)

def parse_actions(text: str) -> list:
    """Simplified, highly surgical parser for CALL: tool(...)"""
    actions = []
    
    # 1. Clean the text and find all CALL: instances
    starts = [m.start() for m in re.finditer(r'CALL:\s*(\w+)\s*\(', text, re.IGNORECASE)]
    
    for i, start_pos in enumerate(starts):
        # We find the matching closing parenthesis for this specific CALL
        # This is much safer than regex for nested structures or trailing junk
        content_from_call = text[start_pos:]
        first_paren = content_from_call.find('(')
        if first_paren == -1: continue
        
        # Balance parentheses to find the correct end
        depth = 0
        last_paren = -1
        for j in range(first_paren, len(content_from_call)):
            if content_from_call[j] == '(': depth += 1
            elif content_from_call[j] == ')':
                depth -= 1
                if depth == 0:
                    last_paren = j
                    break
        
        if last_paren != -1:
            tool_name_match = re.search(r'CALL:\s*(\w+)', content_from_call[:first_paren], re.IGNORECASE)
            if tool_name_match:
                tool_name = tool_name_match.group(1)
                args_raw = content_from_call[first_paren+1:last_paren].strip()
                
                # Auto-wrap positional strings (especially for Linux paths with spaces)
                if not args_raw.startswith('{'):
                    # If it's a quoted string or contains path-like separators
                    if (args_raw.startswith('"') and args_raw.endswith('"')) or '/' in args_raw or '\\' in args_raw:
                        val = args_raw.strip('"\'')
                        args_raw = json.dumps({"path": val})
                    elif ':' in args_raw:
                        args_raw = "{" + args_raw + "}"
                
                try:
                    fixed_args = _fix_json_string(args_raw)
                    args = json.loads(fixed_args)
                    actions.append({"tool": tool_name, "args": args})
                except Exception as e:
                    # Final fallback: try to find anything that looks like JSON inside
                    brace_match = re.search(r'(\{.*\})', args_raw, re.DOTALL)
                    if brace_match:
                        try:
                            args = json.loads(_fix_json_string(brace_match.group(1)))
                            actions.append({"tool": tool_name, "args": args})
                        except: pass
    return actions

def parse_report(text: str) -> str:
    # Look for [REPORT] and take everything until [/REPORT] or end
    # We use a non-greedy match to avoid eating subsequent actions, but greedy enough to get the content
    match = re.search(r'\[REPORT\](.*?)(?:\[/REPORT\]|$)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback: if no [REPORT] tag but has plain text at the end
        if "[ACTION]" not in text and "<THINK>" not in text:
            return text.strip()
        return ""
    return match.group(1).strip()

def parse_think(text: str) -> str:
    match = re.search(r'<THINK>(.*?)</THINK>', text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'<THINK>(.*)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

async def fetch_current_url() -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_BASE}/current_url", timeout=2.0)
            if resp.status_code == 200:
                return resp.json().get("url")
    except (httpx.ConnectError, httpx.ReadTimeout, ConnectionResetError, Exception):
        pass
    return None

async def navigate_to_url(url: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{API_BASE}/navigate", json={"url": url}, timeout=10.0)
    except (httpx.ConnectError, httpx.ReadTimeout, ConnectionResetError, Exception):
        pass

async def chat_with_agent(messages: list, print_callback) -> dict:
    # Ensure system prompt is first
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": get_system_prompt()})
        
    try:
        response = await acompletion(
            model=MODEL,
            messages=messages,
            api_base=API_BASE,
            functions=TOOLS,
            function_call="none",
            stop=["[/ACTION]", "[/REPORT]"]
        )
        
        raw_content = response.choices[0].message.content or ""
        
        # Parse the structured response
        think = parse_think(raw_content)
        actions = parse_actions(raw_content)
        report = parse_report(raw_content)
        
        # User requested to hide THINK blocks in CLI, so we show a minimal indicator
        if think: 
            print_callback("🧠 Thinking...", color="dim")
            
        tool_results = []
        for action in actions:
            t_name = action["tool"]
            t_args = action["args"]
            print_callback(f"⚙️ EXECUTING: {t_name}({json.dumps(t_args)})", color="cyan")
            try:
                res = handle_tool_call(t_name, t_args)
            except Exception as te:
                res = {"error": str(te)}
                
            tool_results.append({
                "tool": t_name,
                "result": res
            })
            
        # FORCE: If there were actions, we IGNORE the report from this turn to prevent hallucination
        final_report = ""
        if report and not actions:
            final_report = report
            print_callback(f"\n{final_report}", color="green")
            
        return {
            "raw": raw_content,
            "actions": actions,
            "tool_results": tool_results,
            "report": final_report
        }
    except (ConnectionResetError, httpx.ConnectError):
        # Silence specific Windows asyncio noise
        return {"error": "Router connection reset. It might still be processing."}
    except Exception as e:
        print_callback(f"LLM Error: {str(e)}", color="red")
        return {"error": str(e)}
