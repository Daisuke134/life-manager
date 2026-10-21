#!/usr/bin/env python3
"""Invoke actual pinned Concordia Island engine on ONLY fictional agent configs.

No personal respondent records, no private personas, no LLM requests. Emitted
raw synthetic logs live only in the isolated CI artifact, not a git commit.
Human validation always reported as unmeasured in a separate directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run(upstream_root: Path, output: Path):
    sys.path.insert(0, str(upstream_root))
    from examples.concordia_island import island_simulation, mock_language_model, run as upstream_run
    from examples.concordia_island.sim.agents import AgentConfig

    fictional = [
        AgentConfig(name="Example Research Agent A", home_place="sunset_apartments",
                    work_place="town_square", personality="cooperative, curious",
                    backstory="A fictional participant in a methodological example."),
        AgentConfig(name="Example Research Agent B", home_place="sunset_apartments",
                    work_place="town_square", personality="reflective, pragmatic",
                    backstory="Another fictional participant in a constructed sandbox."),
    ]
    engine = island_simulation.IslandConcordiaSimulation(
        agent_configs=fictional,
        model=mock_language_model.FastMockLanguageModel(verbose=False),
        embedder=upstream_run.DummyEmbedder(dimension=768),
        engine_type="sequential", setting="island",
        experience_sampling=False, enable_nighttime_social=False,
        enable_nighttime_marketplace=False,
        agent_prefab="esa", max_ticks=4, tick_interval_minutes=120,
    )
    result = engine.play(max_ticks=4)
    raw_logs = engine.get_raw_log()
    html = result.to_html()
    if not html or not raw_logs:
        raise RuntimeError("real engine did not produce a simulation log")
    sim = output / "simulation"
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "simulated_agent_log.html").write_text(html, encoding="utf-8")
    metadata = {
        "engine": "google-deepmind/concordia",
        "source_revision": "7128586aa8c1073bfa09dcb3781cea21e1a49229",
        "mock": True, "simulated_agents": len(fictional),
        "requested_ticks": 4, "emitted_engine_events": len(raw_logs),
        "simulated_log_exists": True, "uses_esa_agent_prefab": True,
        "human_training_data": False, "raw_personal_records": 0,
    }
    (sim / "simulation_summary.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    independent = output / "real_world_validation"
    independent.mkdir(parents=True, exist_ok=True)
    (independent / "verification.json").write_text(
        json.dumps({
            "schema": "manager.concordia.island-mock-verification.v1",
            "real_world_validation_records": 0,
            "human_behavior_fidelity_score": None,
            "empirical_causal_effect": None,
            "socsci210_study_comparison": "NOT_PERFORMED_RIGHTS_HOLD",
            "manager_world_effect": "NONE",
            "reason": "Only fictional agents + deterministic mock model were executed."
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.upstream_root, args.output)


if __name__ == "__main__":
    main()
