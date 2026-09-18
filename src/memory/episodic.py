import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from src.config import GOOGLE_API_KEY, MEM0_API_KEY, ROOT_DIR

logger = logging.getLogger("macrotrack.memory")

class EpisodicMemoryManager:
    """
    Episodic Memory Manager for MacroTrack powered by mem0.
    Stores raw meal entries, daily/weekly summaries, caloric/macro trends,
    and dietary habits with persistent cross-week tracking and reset capabilities.
    """
    def __init__(self):
        self.mem0_instance = None
        self.local_store_path = ROOT_DIR / "episodic_memory_store.json"
        self._init_mem0()

    def _init_mem0(self):
        # Try initializing mem0 with Gemini or local settings
        try:
            from mem0 import Memory
            if GOOGLE_API_KEY:
                config = {
                    "llm": {
                        "provider": "gemini",
                        "config": {
                            "api_key": GOOGLE_API_KEY,
                            "model": "gemini-2.5-flash"
                        }
                    },
                    "embedder": {
                        "provider": "gemini",
                        "config": {
                            "api_key": GOOGLE_API_KEY,
                            "model": "models/text-embedding-004"
                        }
                    },
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "path": str(ROOT_DIR / "qdrant_mem0_data")
                        }
                    }
                }
                self.mem0_instance = Memory.from_config(config)
                logger.info("mem0 initialized with Gemini provider and local Qdrant storage")
            else:
                self.mem0_instance = Memory()
                logger.info("mem0 initialized with default provider")
        except Exception as e:
            logger.warning(f"mem0 advanced initialization fallback to standard episodic store: {e}")
            self.mem0_instance = None

    def _load_local_store(self) -> List[Dict[str, Any]]:
        if self.local_store_path.exists():
            try:
                with open(self.local_store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_local_store(self, items: List[Dict[str, Any]]) -> None:
        try:
            with open(self.local_store_path, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist episodic memory store: {e}")

    def add_meal_episode(self, user_id: str, meal_summary: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        meta = (metadata or {}).copy()
        meta.pop("user_id", None)
        now_iso = datetime.now().isoformat()
        memory_entry = f"Meal Logged [{now_iso}]: {meal_summary}"

        # 1. Store in mem0 if operational
        if self.mem0_instance:
            try:
                self.mem0_instance.add(
                    messages=[{"role": "user", "content": memory_entry}],
                    user_id=user_id,
                    metadata=meta
                )
            except Exception as e:
                logger.warning(f"mem0.add failed ({e}); recorded in local journal.")

        # 2. Always persist in local episodic journal for fast offline query & test guarantees
        local_store = self._load_local_store()
        local_store.append({
            "type": "meal",
            "user_id": user_id,
            "text": memory_entry,
            "metadata": meta,
            "timestamp": now_iso
        })
        self._save_local_store(local_store)

    def add_summary_episode(self, user_id: str, summary_type: str, summary_text: str, metrics: Optional[Dict[str, Any]] = None) -> None:
        meta = metrics or {}
        meta["summary_type"] = summary_type
        now_iso = datetime.now().isoformat()
        entry = f"{summary_type.upper()} SUMMARY [{now_iso}]: {summary_text}"

        if self.mem0_instance:
            try:
                self.mem0_instance.add(
                    messages=[{"role": "assistant", "content": entry}],
                    user_id=user_id,
                    metadata=meta
                )
            except Exception as e:
                logger.warning(f"mem0.add summary failed: {e}")

        local_store = self._load_local_store()
        local_store.append({
            "type": "summary",
            "user_id": user_id,
            "text": entry,
            "metadata": meta,
            "timestamp": now_iso
        })
        self._save_local_store(local_store)

    def query_episodes(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Check mem0 first
        results = []
        if self.mem0_instance:
            try:
                mem_res = self.mem0_instance.search(query=query, user_id=user_id, limit=limit)
                if mem_res and isinstance(mem_res, dict) and "results" in mem_res:
                    return mem_res["results"]
                elif isinstance(mem_res, list) and len(mem_res) > 0:
                    return mem_res
            except Exception as e:
                logger.warning(f"mem0.search failed: {e}")

        # Local journal keyword / recency query
        local_store = self._load_local_store()
        user_entries = [e for e in local_store if e.get("user_id") == user_id]
        keywords = query.lower().split()

        scored = []
        for e in user_entries:
            text = e.get("text", "").lower()
            score = sum(1 for kw in keywords if kw in text)
            scored.append((score, e))

        scored.sort(key=lambda x: (x[0], x[1].get("timestamp", "")), reverse=True)
        return [item[1] for item in scored[:limit]]

    def reset_memory(self, user_id: str) -> bool:
        if self.mem0_instance:
            try:
                self.mem0_instance.delete_all(user_id=user_id)
            except Exception as e:
                logger.warning(f"mem0.delete_all warning: {e}")

        local_store = self._load_local_store()
        updated = [e for e in local_store if e.get("user_id") != user_id]
        self._save_local_store(updated)
        return True

# Global episodic memory instance
memory = EpisodicMemoryManager()
