
import json
import os

class ProjectManager:
    def __init__(self,default_project,projects_root):
        self.current_project = default_project
        self.projects_root = projects_root
        self.ensure_project_exists(default_project)
        
    def get_project_dir(self, project_name: str = None):
        if project_name is None:
            project_name = self.current_project
        return os.path.join(self.projects_root, project_name)

    def ensure_project_exists(self, project_name: str):
        p_dir = os.path.join(self.projects_root, project_name)
        os.makedirs(os.path.join(p_dir, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(p_dir, "graph_db"), exist_ok=True)
        
        hist_file = os.path.join(p_dir, "history.json")
        if not os.path.exists(hist_file):
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump([], f)
                
        files_record = os.path.join(p_dir, "files.json")
        if not os.path.exists(files_record):
            with open(files_record, "w", encoding="utf-8") as f:
                json.dump([], f)
                
        return p_dir

    def list_projects(self):
        if not os.path.exists(self.projects_root):
            return []
        return [d for d in os.listdir(self.projects_root) if os.path.isdir(os.path.join(self.projects_root, d))]

    def switch_project(self, project_name: str):
        if project_name not in self.list_projects():
            raise ValueError(f"Project {project_name} does not exist")
        self.current_project = project_name
        return self.get_project_dir(project_name)

    def get_file_records(self):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        try:
            if os.path.exists(record_path):
                with open(record_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
        except:
            return []

    def add_file_record(self, record: dict):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        records.insert(0, record) 
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def update_file_status(self, file_id: str, status: str, message: str):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        updated = False
        for rec in records:
            if rec.get("id") == file_id:
                rec["status"] = status
                rec["message"] = message
                updated = True
                break
        if updated:
            with open(record_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

    def remove_file_record(self, file_id: str):
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        records = [r for r in records if r.get("id") != file_id]
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def update_file_info(self, file_id: str, updates: dict):
        """
        更新文件的元数据 (例如 last_graph_sync, status, message 等)
        :param file_id: 文件ID
        :param updates: 包含要更新字段的字典, 例如 {"last_graph_sync": 171890..., "status": "indexed"}
        """
        record_path = os.path.join(self.get_project_dir(), "files.json")
        records = self.get_file_records()
        updated = False
        
        for rec in records:
            if rec.get("id") == file_id:
                # 遍历字典，更新所有传入的字段
                for key, value in updates.items():
                    rec[key] = value
                updated = True
                break
        
        if updated:
            with open(record_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        return updated
