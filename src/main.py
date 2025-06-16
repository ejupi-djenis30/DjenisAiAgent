import robot
import os
import sys

def run_agent_tasks():
    print("--- Starting DjenisAiAgent via Robot Framework Orchestrator ---")

    project_root = os.path.dirname(os.path.dirname(__file__))

    suite_path = os.path.join(project_root, "robot", "tasks.robot")
    output_dir = os.path.join(project_root, "results")

    if not os.path.exists(suite_path):
        print(f"Error: Robot Framework suite not found at {suite_path}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    try:
        result = robot.run(
            suite_path,
            outputdir=output_dir,
            logtitle="Agent Execution Log",
            reporttitle="Agent Execution Report",
            name="DjenisAiAgent Tasks"
        )

        if result == 0:
            print("\n--- Agent tasks completed successfully. ---")
            print(f"Full log and report are available in the '{output_dir}' directory.")
        else:
            print(f"\n--- Agent tasks completed with {result} errors. ---")
            print(f"Check the log and report in the '{output_dir}' directory for details.")

    except Exception as e:
        print(f"\nAn unexpected error occurred while running the Robot Framework suite: {e}")

if __name__ == "__main__":
    run_agent_tasks()
