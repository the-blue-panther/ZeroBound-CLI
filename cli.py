import sys
import asyncio
import argparse
from colorama import init, Fore, Style
import db_manager
from agent import chat_with_agent, fetch_current_url, navigate_to_url
from zb_tools import TOOLS

init(autoreset=True)

ASCII_ART = """
  ______              ____                        _    _____ _      _____ 
 |___  /             |  _ \                      | |  / ____| |    |_   _|
    / / ___ _ __ ___ | |_) | ___  _   _ _ __   __| | | |    | |      | |  
   / / / _ \ '__/ _ \|  _ < / _ \| | | | '_ \ / _` | | |    | |      | |  
  / /_|  __/ | | (_) | |_) | (_) | |_| | | | | (_| | | |____| |____ _| |_ 
 /_____\\___|_|  \\___/|____/ \\___/ \\__,_|_| |_|\\__,_|  \\_____|______|_____|
                                                                          
"""

current_session_id = None
messages = []

def print_help():
    print(Fore.YELLOW + "--- ZeroBound CLI Commands ---")
    print(Fore.CYAN + "help" + Fore.WHITE + "       : Show this help message")
    print(Fore.CYAN + "history" + Fore.WHITE + "    : Show recent chat sessions")
    print(Fore.CYAN + "resume <id>" + Fore.WHITE + ": Resume a past session and open its web URL")
    print(Fore.CYAN + "restart" + Fore.WHITE + "    : Start a completely new session")
    print(Fore.CYAN + "exit / quit" + Fore.WHITE + ": Exit the CLI")
    print(Fore.YELLOW + "\n--- Available Agent Tools ---")
    for t in TOOLS:
        print(f"• {t['name']}: {t['description']}")
    print("")

def print_history():
    sessions = db_manager.get_recent_sessions(10)
    print(Fore.YELLOW + "--- Recent Sessions ---")
    for s in sessions:
        print(f"ID: {s['id']} | Last Active: {s['updated_at']} | URL: {s['url'] or 'None'}")
    print("")

async def resume_session(session_id: int):
    global current_session_id, messages
    url, loaded_msgs = db_manager.load_session(session_id)
    if loaded_msgs is not None:
        current_session_id = session_id
        messages = loaded_msgs
        print(Fore.GREEN + f"Resumed session {session_id} with {len(messages)} messages.")
        if url:
            print(Fore.CYAN + f"Navigating to DeepSeek URL: {url}...")
            await navigate_to_url(url)
            print(Fore.GREEN + "Navigation complete.")
    else:
        print(Fore.RED + f"Session {session_id} not found.")

def start_new_session():
    global current_session_id, messages
    current_session_id = db_manager.create_session()
    messages = []
    print(Fore.GREEN + f"Started new session {current_session_id}.")

def console_print(text: str, color: str = "white"):
    color_map = {
        "white": Fore.WHITE,
        "cyan": Fore.CYAN,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "red": Fore.RED,
        "dim": Style.DIM + Fore.WHITE
    }
    print(color_map.get(color, Fore.WHITE) + text + Style.RESET_ALL)

async def main_loop():
    print(Fore.CYAN + ASCII_ART)
    print(Fore.YELLOW + "Welcome to ZeroBound CLI. Type 'help' for commands.")
    
    start_new_session()
    
    while True:
        try:
            user_input = input(Fore.MAGENTA + "zb> " + Fore.WHITE).strip()
            if not user_input:
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                break
            elif user_input.lower() == 'help':
                print_help()
                continue
            elif user_input.lower() == 'history':
                print_history()
                continue
            elif user_input.lower() == 'restart':
                start_new_session()
                continue
            elif user_input.lower().startswith('resume '):
                try:
                    sid = int(user_input.split()[1])
                    await resume_session(sid)
                except ValueError:
                    print(Fore.RED + "Invalid session ID.")
                continue

            # Add user message
            messages.append({"role": "user", "content": user_input})
            db_manager.save_session(current_session_id, None, messages) # Save before request
            
            # Chat with agent (auto-loops for tool calls if needed)
            max_iterations = 10
            for i in range(max_iterations):
                result = await chat_with_agent(messages, console_print)
                
                if "error" in result:
                    break
                    
                raw = result["raw"]
                messages.append({"role": "assistant", "content": raw})
                
                if result["tool_results"]:
                    # Agent used tools, append results and loop
                    tool_msg = ""
                    for res in result["tool_results"]:
                        tool_msg += f"Result for {res['tool']}:\n{res['result']}\n\n"
                    messages.append({"role": "user", "content": f"[TOOL RESULTS]\n{tool_msg}"})
                else:
                    # Agent finished
                    break
                    
            # After interaction, save history and update URL
            current_url = await fetch_current_url()
            db_manager.save_session(current_session_id, current_url, messages)
            
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\nUse 'exit' to quit.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")

if __name__ == "__main__":
    import subprocess
    import time
    import os
    
    # Pre-flight check
    if not os.path.exists("profiles/deepseek/state.json"):
        print(Fore.RED + "\n[ERROR] No DeepSeek session found!")
        print(Fore.YELLOW + "You must log in to DeepSeek before starting the CLI.")
        print(Fore.WHITE + "Run this command first:")
        print(Fore.CYAN + "  python router/manual_login.py deepseek\n")
        sys.exit(1)
        
    print(Fore.CYAN + "Starting ZeroBound Web Router...")
    router_log = open("router.log", "a", encoding="utf-8")
    router_process = subprocess.Popen(
        [sys.executable, "router/server.py"], 
        stdout=router_log, 
        stderr=router_log,
        bufsize=1 # Line buffered
    )
    time.sleep(4) # Give it a bit more time to initialize
    
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
    finally:
        print(Fore.CYAN + "Shutting down ZeroBound Web Router...")
        router_process.terminate()
        router_process.wait()
        router_log.close()
    print(Fore.CYAN + "Goodbye!")
