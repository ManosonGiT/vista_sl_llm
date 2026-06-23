"""
RAG Engine — Optimized for Module-based guidance.
"""

import os
from backend.logging_config import logger

CURRICULUM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "curriculum", "curriculum.txt"))

# Module-level references
_modules = {} # { "Module Name": [ {lesson_dict}, ... ] }
_all_titles = []


def _parse_curriculum():
    global _all_titles
    current = {}
    if not os.path.exists(CURRICULUM_PATH): 
        logger.warning(f"Curriculum path {CURRICULUM_PATH} does not exist.")
        return

    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line == "---":
                if current:
                    mod_name = current.get("module", "General")
                    if mod_name not in _modules: _modules[mod_name] = []
                    _modules[mod_name].append(current)
                    _all_titles.append(current.get("title"))
                current = {}
            elif ":" in line:
                key, val = line.split(":", 1)
                current[key.strip().lower().replace("lesson_id", "id")] = val.strip()
        
        if current:
            mod_name = current.get("module", "General")
            if mod_name not in _modules: _modules[mod_name] = []
            _modules[mod_name].append(current)

def init_rag():
    logger.info("Parsing Curriculum into Modules...")
    _parse_curriculum()
    logger.info(f"Loaded {len(_modules)} Modules and {len(_all_titles)} Lessons.")

def get_module_list():
    """Returns unique module names."""
    return list(_modules.keys())

def get_next_lesson_in_module(module_name: str, finished_titles: list[str]):
    """
    Finds the first lesson in a module that isn't in the finished list.
    """
    lessons = _modules.get(module_name, [])
    for lesson in lessons:
        if lesson.get("title") not in finished_titles:
            return lesson
    return None

def get_all_lesson_titles():
    return _all_titles

def search_curriculum(query: str, top_k: int = 3) -> str:
    """
    Simple keyword search to find matching lessons in the curriculum.
    Returns a formatted string containing the relevant lessons and links.
    """
    if not query:
        return ""
    
    query_lower = query.lower()
    matches = []
    
    for mod_name, lessons in _modules.items():
        for lesson in lessons:
            title = lesson.get("title", "")
            mod = lesson.get("module", "")
            if (query_lower in title.lower()) or (query_lower in mod.lower()) or (title.lower() in query_lower):
                matches.append(lesson)
                
    # Limit to top_k
    matches = matches[:top_k]
    
    if not matches:
        return "RELEVANT LESSONS:\nNo specific lessons matched your query in the curriculum database."
        
    context = "RELEVANT LESSONS:\n"
    for l in matches:
        context += f"- Lesson ID: {l.get('id')}\n  Title: {l.get('title')}\n  Module: {l.get('module')}\n"
    return context
