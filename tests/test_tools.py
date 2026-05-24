"""Tests for MCP tool registration and metadata."""

import pytest

from strava_sport_science_mcp.server import mcp


def test_all_tools_registered() -> None:
    """Test that all 8 tools are registered on the MCP server."""
    tools = mcp.list_tools()
    tool_names = {tool.name for tool in tools}

    expected_tools = {
        "get_activities",
        "get_activity_detail",
        "get_athlete_profile",
        "get_activity_streams",
        "get_training_load",
        "get_zone_distribution",
        "get_fitness_trend",
        "get_race_readiness",
    }

    assert expected_tools <= tool_names, f"Missing tools. Have: {tool_names}"


def test_tool_descriptions() -> None:
    """Test that all tools have descriptions."""
    tools = mcp.list_tools()

    for tool in tools:
        assert tool.description is not None, f"Tool {tool.name} has no description"
        assert len(tool.description) > 10, (
            f"Tool {tool.name} has a very short description: {tool.description}"
        )


def test_raw_tools_have_correct_params() -> None:
    """Test that raw tools have expected parameters."""
    tools = mcp.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    # get_activities should have days_back parameter
    get_activities_tool = tools_by_name.get("get_activities")
    assert get_activities_tool is not None
    assert "days_back" in {p.name for p in get_activities_tool.inputSchema.properties.keys()}

    # get_activity_detail should have activity_id parameter
    get_detail_tool = tools_by_name.get("get_activity_detail")
    assert get_detail_tool is not None
    assert "activity_id" in {p.name for p in get_detail_tool.inputSchema.properties.keys()}


def test_sport_science_tools_have_correct_params() -> None:
    """Test that sport-science tools have expected parameters."""
    tools = mcp.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    # get_training_load should have days parameter
    training_load_tool = tools_by_name.get("get_training_load")
    assert training_load_tool is not None
    assert "days" in {p.name for p in training_load_tool.inputSchema.properties.keys()}

    # get_zone_distribution should have days parameter
    zone_tool = tools_by_name.get("get_zone_distribution")
    assert zone_tool is not None
    assert "days" in {p.name for p in zone_tool.inputSchema.properties.keys()}

    # get_fitness_trend should have weeks parameter
    trend_tool = tools_by_name.get("get_fitness_trend")
    assert trend_tool is not None
    assert "weeks" in {p.name for p in trend_tool.inputSchema.properties.keys()}

    # get_race_readiness should have target_distance_km parameter
    readiness_tool = tools_by_name.get("get_race_readiness")
    assert readiness_tool is not None
    assert "target_distance_km" in {
        p.name for p in readiness_tool.inputSchema.properties.keys()
    }
