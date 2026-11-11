import json

from live_notes_api.tools import TOOL_NAMES, TOOLS, InvalidToolCall, parse_tool_call


def test_eight_tools_strict_and_closed():
    assert TOOL_NAMES == [
        "insert_block",
        "update_block",
        "delete_block",
        "move_block",
        "upsert_diagram",
        "annotate_slide",
        "set_slide",
        "close_section",
    ]

    def check(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert sorted(schema["required"]) == sorted(schema["properties"])
            for v in schema["properties"].values():
                check(v)
        for v in schema.get("anyOf", []):
            check(v)
        if "items" in schema:
            check(schema["items"])

    for t in TOOLS:
        assert t["strict"] is True and t["description"]
        check(t["input_schema"])
    json.dumps(TOOLS)  # serialisable, deterministic order


def test_model_never_supplies_ids_or_coordinates():
    props = {t["name"]: t["input_schema"]["properties"] for t in TOOLS}
    assert "id" not in props["insert_block"] and "ref" in props["insert_block"]
    flat = json.dumps(TOOLS)
    for forbidden in ('"rect"', '"rects"', '"x"', '"y"', '"w"', '"h"'):
        assert forbidden not in flat
    assert "region" in flat and "quote" in flat


def test_parse_tool_call():
    c = parse_tool_call(
        "annotate_slide",
        {"slide": 1, "target": {"region": "r4"}, "style": "circle", "note": None},
        "tu_1",
    )
    assert c.name == "annotate_slide" and c.call_id == "tu_1"
    bad = [
        parse_tool_call(
            "annotate_slide", {"slide": 1, "target": {"x": 1}, "style": "circle", "note": None}
        ),
        parse_tool_call(
            "insert_block", {"after": "end", "kind": "bullet", "depth": 3, "text": "t", "src": []}
        ),
        parse_tool_call("nope", {}),
    ]
    assert all(isinstance(b, InvalidToolCall) for b in bad)
