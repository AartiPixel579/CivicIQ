import os
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from .config import DEPARTMENTS_DIR, ACTIVE_DEPARTMENTS
from .models import DepartmentConfig, FlowDefinition, KnowledgeLink

logger = logging.getLogger("department_loader")

class DepartmentRegistry:
    def __init__(self, departments_dir: Path = DEPARTMENTS_DIR):
        self.departments_dir = Path(departments_dir)
        self.departments: Dict[str, DepartmentConfig] = {}
        self.flows: Dict[str, Dict[str, FlowDefinition]] = {} # dept_id -> {flow_id: FlowDefinition}
        self.knowledge_links: Dict[str, List[KnowledgeLink]] = {} # dept_id -> list of links
        self.services: Dict[str, List[Dict]] = {} # dept_id -> list of services
        self.load_all()

    def reload(self):
        """Reloads all departments dynamically."""
        self.departments.clear()
        self.flows.clear()
        self.knowledge_links.clear()
        self.services.clear()
        self.load_all()

    def load_all(self):
        if not self.departments_dir.exists():
            logger.warning(f"Departments directory not found at {self.departments_dir}")
            return

        for entry in os.scandir(self.departments_dir):
            if entry.is_dir():
                dept_id = entry.name
                self._load_department(dept_id, Path(entry.path))

        logger.info(f"Loaded {len(self.departments)} departments: {list(self.departments.keys())}")

    def _load_department(self, dept_id: str, dept_path: Path):
        # 1. Config
        config_path = dept_path / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    self.departments[dept_id] = DepartmentConfig(**config_data)
            except Exception as e:
                logger.error(f"Error loading config for {dept_id}: {e}")

        # 2. Flows (authoritative top-level flows.json)
        flows_path = dept_path / "flows.json"
        if flows_path.exists():
            try:
                with open(flows_path, "r", encoding="utf-8") as f:
                    flows_data = json.load(f)
                    dept_flows = {}
                    for item in flows_data.get("flows", []):
                        flow = FlowDefinition(**item)
                        dept_flows[flow.id] = flow
                    self.flows[dept_id] = dept_flows
            except Exception as e:
                logger.error(f"Error loading flows for {dept_id}: {e}")

        # 3. Knowledge Links
        links_path = dept_path / "knowledge_links.json"
        if links_path.exists():
            try:
                with open(links_path, "r", encoding="utf-8") as f:
                    links_data = json.load(f)
                    links_list = []
                    for item in links_data.get("links", []):
                        links_list.append(KnowledgeLink(**item))
                    self.knowledge_links[dept_id] = links_list
            except Exception as e:
                logger.error(f"Error loading links for {dept_id}: {e}")

        # 4. Services catalog (if exists)
        services_path = dept_path / "services" / "services.json"
        if services_path.exists():
            try:
                with open(services_path, "r", encoding="utf-8") as f:
                    services_data = json.load(f)
                    self.services[dept_id] = services_data.get("services", [])
            except Exception as e:
                logger.error(f"Error loading services for {dept_id}: {e}")

    def is_active(self, dept_id: str) -> bool:
        """Checks if a department is active in the current MVP."""
        if dept_id in ACTIVE_DEPARTMENTS:
            dept = self.departments.get(dept_id)
            if dept and dept.active is not False:
                return True
        return False

    def get_services_for_dept(self, dept_id: str) -> List[Dict]:
        return self.services.get(dept_id, [])

    def get_departments(self) -> List[DepartmentConfig]:
        return list(self.departments.values())

    def get_department(self, dept_id: str) -> Optional[DepartmentConfig]:
        return self.departments.get(dept_id)

    def get_flows_for_dept(self, dept_id: str) -> List[FlowDefinition]:
        return list(self.flows.get(dept_id, {}).values())

    def get_flow(self, dept_id: str, flow_id: str) -> Optional[FlowDefinition]:
        return self.flows.get(dept_id, {}).get(flow_id)

    def find_flow_by_id(self, flow_id: str) -> Optional[tuple[str, FlowDefinition]]:
        """Finds flow across any department by flow_id."""
        for dept_id, flows in self.flows.items():
            if flow_id in flows:
                return dept_id, flows[flow_id]
        return None

    def get_forms_dir(self, dept_id: str) -> Path:
        return self.departments_dir / dept_id / "forms"

    def get_form_path(self, dept_id: str, form_filename: str) -> Optional[Path]:
        form_path = self.get_forms_dir(dept_id) / form_filename
        if form_path.exists() and form_path.is_file():
            return form_path
        return None

    def list_forms_for_dept(self, dept_id: str) -> List[str]:
        forms_dir = self.get_forms_dir(dept_id)
        if not forms_dir.exists():
            return []
        return [f.name for f in forms_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]

# Global registry instance
registry = DepartmentRegistry()
