class FileSystemTool:
    def __init__(self):
        pass

    def read_file(self, file_path):
        with open(file_path, 'r') as file:
            return file.read()

    def write_file(self, file_path, content):
        with open(file_path, 'w') as file:
            file.write(content)

    def delete_file(self, file_path):
        import os
        if os.path.exists(file_path):
            os.remove(file_path)

    def list_directory(self, dir_path):
        import os
        return os.listdir(dir_path)

    def create_directory(self, dir_path):
        import os
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)