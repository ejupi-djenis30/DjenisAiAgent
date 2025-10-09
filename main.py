"""Main entry point for the AI Agent."""

import sys
import argparse
from colorama import init, Fore, Style

from src.utils.logger import setup_logger
from src.config.config import config
from src.core.agent import EnhancedAIAgent

# Initialize colorama for Windows
init(autoreset=True)

logger = setup_logger("Main", config.logs_dir, config.log_level)


def main():
    """Main function."""
    
    parser = argparse.ArgumentParser(
        description="AI Agent for Windows UI Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "open notepad and type hello world"
  python main.py "search google for python tutorials"
  python main.py "open calculator and calculate 25 * 4"
  
Emergency Stop: Press Ctrl+Shift+Q during execution
        """
    )
    
    parser.add_argument(
        "request",
        nargs="*",
        help="The task request for the agent"
    )
    
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    
    parser.add_argument(
        "--stats",
        "-s",
        action="store_true",
        help="Show execution statistics"
    )
    
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable overlay UI"
    )

    parser.add_argument(
        "--no-limit-mode",
        action="store_true",
        help="Disable safety ceilings (retries, timeouts, token limits) for long or complex runs"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        config.debug_mode = True
        logger.setLevel("DEBUG")

    if args.no_limit_mode:
        config.apply_no_limit_mode()
        logger.warning("No-limit mode enabled: safety ceilings lifted")
    
    # Print banner
    print(f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║        🤖 AI Agent for Windows UI Automation 🤖          ║
║                                                           ║
║              Powered by Google Gemini                     ║
║                    Version 2.0                            ║
║{f"           UI Overlay: {'Disabled' if args.no_ui else 'Enabled'}".center(59)}║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """)
    
    try:
        # Initialize enhanced agent with UI preference
        agent = EnhancedAIAgent(use_ui=not args.no_ui)
        
        if args.interactive or not args.request:
            # Interactive mode
            print(f"{Fore.YELLOW}Interactive Mode{Style.RESET_ALL} - Type 'exit', 'quit', or 'help' for assistance\n")
            
            while True:
                try:
                    request = input(f"\n{Fore.GREEN}🎯 Enter your request: {Style.RESET_ALL}").strip()
                    
                    if not request:
                        continue
                    
                    if request.lower() in ['exit', 'quit', 'q']:
                        print(f"\n{Fore.CYAN}👋 Goodbye!{Style.RESET_ALL}")
                        break
                    
                    if request.lower() == 'help':
                        print(f"""
{Fore.CYAN}Available Commands:{Style.RESET_ALL}
  • help     - Show this help message
  • exit     - Exit the program
  • stats    - Show execution statistics
  
{Fore.CYAN}Example Requests:{Style.RESET_ALL}
  • "open notepad and type hello world"
  • "search google for python tutorials"
  • "open calculator and calculate 25 * 4"
  • "take a screenshot"
  
{Fore.YELLOW}Emergency Stop:{Style.RESET_ALL} Press Ctrl+Shift+Q during execution
                        """)
                        continue
                    
                    if request.lower() == 'stats':
                        stats = agent.get_stats()
                        print(f"\n{Fore.CYAN}📊 Execution Statistics:{Style.RESET_ALL}")
                        print(f"  Total Tasks: {stats['total_tasks']}")
                        print(f"  Successful: {stats['successful_tasks']}")
                        print(f"  Failed: {stats['failed_tasks']}")
                        print(f"  Success Rate: {stats['success_rate']:.1f}%")
                        print(f"  Total Actions: {stats['total_actions']}")
                        print(f"  Avg Time/Task: {stats['avg_execution_time']:.1f}s")
                        continue
                    
                    # Execute task
                    result = agent.execute_task(request)
                    
                    # Handle clarification
                    if result.get("needs_clarification"):
                        print(f"\n{Fore.YELLOW}❓ {result['question']}{Style.RESET_ALL}")
                        continue
                    
                except KeyboardInterrupt:
                    print(f"\n\n{Fore.CYAN}👋 Interrupted by user. Goodbye!{Style.RESET_ALL}")
                    break
                except Exception as e:
                    logger.error(f"Error in interactive mode: {e}", exc_info=True)
                    print(f"\n{Fore.RED}❌ Error: {e}{Style.RESET_ALL}")
        
        else:
            # Single command mode
            request = " ".join(args.request)
            result = agent.execute_task(request)
            
            # Show stats if requested
            if args.stats:
                stats = agent.get_stats()
                print(f"\n{Fore.CYAN}📊 Execution Statistics:{Style.RESET_ALL}")
                print(f"  Execution Time: {stats['avg_execution_time']:.2f}s")
                print(f"  Total Actions: {stats['total_actions']}")
                print(f"  Success: {result.get('success', False)}")
            
            # Handle clarification
            if result.get("needs_clarification"):
                print(f"\n{Fore.YELLOW}❓ {result['question']}{Style.RESET_ALL}")
                
                # Get clarification
                clarification = input(f"\n{Fore.GREEN}🎯 Your answer: {Style.RESET_ALL}").strip()
                if clarification:
                    full_request = f"{request}. {clarification}"
                    result = agent.execute_task(full_request)
            
            # Exit with appropriate code
            sys.exit(0 if result.get("success", False) else 1)
    
    except KeyboardInterrupt:
        print(f"\n\n{Fore.CYAN}👋 Interrupted by user. Goodbye!{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n{Fore.RED}❌ Fatal error: {e}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
