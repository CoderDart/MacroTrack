import json
import logging
from typing import Dict, Any, List, Optional
import networkx as nx
from src.config import KG_PATH, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger("macrotrack.graph")

class NutritionKnowledgeGraph:
    """
    Nutrition Knowledge Graph Engine for MacroTrack.
    Models multi-hop relationships: Food -> Nutrient -> Health Outcome -> User Goal.
    Provides native NetworkX graph reasoning with Neo4j driver compatibility.
    """
    def __init__(self):
        self.graph = nx.DiGraph()
        self.neo4j_driver = None
        self._load_networkx_graph()
        self._try_init_neo4j()

    def _load_networkx_graph(self):
        if not KG_PATH.exists():
            logger.warning(f"Knowledge graph file not found at {KG_PATH}")
            return

        with open(KG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        for node in data.get("nodes", []):
            self.graph.add_node(
                node["id"],
                label=node.get("label", node["id"]),
                type=node.get("type", "Entity"),
                category=node.get("category", ""),
                dietary=node.get("dietary", ""),
                protein_density_score=node.get("protein_density_score", 0.0),
                system=node.get("system", "")
            )

        for edge in data.get("edges", []):
            self.graph.add_edge(
                edge["source"],
                edge["target"],
                relation=edge.get("relation", "RELATES_TO"),
                weight=edge.get("weight", 1.0)
            )
        logger.info(f"Loaded Knowledge Graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

    def _try_init_neo4j(self):
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            # Test connectivity
            with driver.session() as session:
                session.run("RETURN 1")
            self.neo4j_driver = driver
            logger.info("Connected to live Neo4j instance.")
        except Exception as e:
            logger.info(f"Neo4j live instance unavailable ({e}); using embedded NetworkX graph engine.")
            self.neo4j_driver = None

    def query_foods_for_goal(self, goal_id_or_keyword: str) -> List[Dict[str, Any]]:
        """
        Traverse backward from goal -> outcomes -> nutrients -> foods.
        """
        target_goal_nodes = []
        term = goal_id_or_keyword.lower()
        for n, d in self.graph.nodes(data=True):
            if d.get("type") == "UserGoal" and (term in n.lower() or term in d.get("label", "").lower()):
                target_goal_nodes.append(n)

        if not target_goal_nodes:
            # Fallback to muscle gain or weight loss if nothing matched
            target_goal_nodes = ["goal_muscle_gain"] if "protein" in term or "muscle" in term else ["goal_weight_loss"]

        results = []
        for g_node in target_goal_nodes:
            g_label = self.graph.nodes[g_node].get("label")
            # In-edges to goal are outcomes
            outcomes = list(self.graph.predecessors(g_node))
            for o in outcomes:
                o_label = self.graph.nodes[o].get("label")
                # In-edges to outcome are nutrients
                nutrients = list(self.graph.predecessors(o))
                for nutr in nutrients:
                    nutr_label = self.graph.nodes[nutr].get("label")
                    # In-edges to nutrient are foods
                    foods = list(self.graph.predecessors(nutr))
                    for f in foods:
                        f_data = self.graph.nodes[f]
                        results.append({
                            "food_id": f,
                            "food_name": f_data.get("label"),
                            "category": f_data.get("category"),
                            "dietary": f_data.get("dietary"),
                            "protein_density": f_data.get("protein_density_score", 0.0),
                            "nutrient": nutr_label,
                            "health_outcome": o_label,
                            "goal": g_label
                        })

        # Remove duplicates while preserving richest relations
        unique_foods = {}
        for r in results:
            fid = r["food_id"]
            if fid not in unique_foods:
                unique_foods[fid] = r
        return list(unique_foods.values())

    def get_protein_density_leaderboard(self, dietary_pref: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ranks foods by protein density (protein per calorie)
        Answering: 'Which foods help me reach protein target fastest?'
        """
        food_nodes = [
            (n, d) for n, d in self.graph.nodes(data=True)
            if d.get("type") == "Food"
        ]
        leaderboard = []
        for n, d in food_nodes:
            if dietary_pref and dietary_pref != "all":
                if dietary_pref == "veg" and d.get("dietary") not in ["veg"]:
                    continue
                if dietary_pref == "ovo-veg" and d.get("dietary") not in ["veg", "ovo-veg"]:
                    continue

            # Find connected nutrients & outcomes
            nutrients = [self.graph.nodes[t].get("label") for t in self.graph.successors(n) if self.graph.nodes[t].get("type") == "Nutrient"]
            leaderboard.append({
                "food_id": n,
                "food_name": d.get("label"),
                "category": d.get("category"),
                "dietary": d.get("dietary"),
                "protein_density_score": d.get("protein_density_score", 0.0),
                "key_nutrients": nutrients
            })

        leaderboard.sort(key=lambda x: x["protein_density_score"], reverse=True)
        return leaderboard

    def explain_food_pathway(self, food_name_query: str) -> Optional[Dict[str, Any]]:
        """
        Traces forward: Food -> Nutrient -> Outcome -> Goal
        """
        q = food_name_query.lower()
        matched_node = None
        for n, d in self.graph.nodes(data=True):
            if d.get("type") == "Food" and (q in n.lower() or q in d.get("label", "").lower()):
                matched_node = n
                break

        if not matched_node:
            return None

        food_info = self.graph.nodes[matched_node]
        pathways = []

        for nutr in self.graph.successors(matched_node):
            edge_f_n = self.graph.get_edge_data(matched_node, nutr)
            nutr_info = self.graph.nodes[nutr]
            for outcome in self.graph.successors(nutr):
                edge_n_o = self.graph.get_edge_data(nutr, outcome)
                outcome_info = self.graph.nodes[outcome]
                for goal in self.graph.successors(outcome):
                    edge_o_g = self.graph.get_edge_data(outcome, goal)
                    goal_info = self.graph.nodes[goal]
                    pathways.append({
                        "nutrient": nutr_info.get("label"),
                        "food_relation": edge_f_n.get("relation"),
                        "health_outcome": outcome_info.get("label"),
                        "outcome_relation": edge_n_o.get("relation"),
                        "target_goal": goal_info.get("label"),
                        "goal_relation": edge_o_g.get("relation")
                    })

        return {
            "food_id": matched_node,
            "food_name": food_info.get("label"),
            "category": food_info.get("category"),
            "dietary": food_info.get("dietary"),
            "protein_density_score": food_info.get("protein_density_score"),
            "pathways": pathways
        }

    def get_all_graph_elements(self) -> Dict[str, Any]:
        """
        Returns full graph schema for frontend rendering.
        """
        nodes = []
        for n, d in self.graph.nodes(data=True):
            nodes.append({
                "id": n,
                "label": d.get("label", n),
                "type": d.get("type", "Entity"),
                "category": d.get("category", "")
            })
        edges = []
        for u, v, d in self.graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", "")
            })
        return {"nodes": nodes, "edges": edges}

# Global Knowledge Graph instance
kg = NutritionKnowledgeGraph()
