class PowerShellTool:
    def __init__(self):
        pass

    def execute_command(self, command):
        import subprocess
        result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True)
        return result.stdout, result.stderr

    def get_process_list(self):
        command = "Get-Process | Select-Object -Property Name, Id"
        return self.execute_command(command)

    def stop_process(self, process_id):
        command = f"Stop-Process -Id {process_id} -Force"
        return self.execute_command(command)

    def start_process(self, process_name):
        command = f"Start-Process {process_name}"
        return self.execute_command(command)