"""Async subgraph of notebook chat; upstream owns conversation checkpoints."""

import json
from typing import Any

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.databridge.research_models import Proposal, Synthesis
from open_notebook.exceptions import InvalidInputError, OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content


class ResearchState(TypedDict, total=False):
    phase: str
    model_id: str | None
    input: dict[str, Any]
    output: dict[str, Any]


async def structured_call(state: ResearchState, template: str, schema) -> dict:
    payload = [
        SystemMessage(
            content=Prompter(prompt_template=template).render(
                data={"schema": schema.model_json_schema()}
            )
        ),
        HumanMessage(content=json.dumps(state["input"], ensure_ascii=False)),
    ]
    if len(payload[1].content) > 160000:
        raise InvalidInputError("Research context exceeds the bounded planning budget")
    try:
        model = await provision_langchain_model(
            str(payload), state.get("model_id"), "chat", max_tokens=4096
        )
        message = await model.ainvoke(payload)
        content = clean_thinking_content(extract_text_content(message.content))
        if len(content) > 32768:
            raise ValueError("Output limit")
        result = schema.model_validate_json(content)
        return {"output": result.model_dump()}
    except OpenNotebookError:
        raise
    except ValueError:
        raise InvalidInputError(
            "Model response did not match the bounded research schema"
        ) from None
    except Exception as error:
        kind, safe = classify_error(error)
        raise kind(safe) from None


async def plan_node(state: ResearchState):
    return await structured_call(state, "databridge/plan", Proposal)


async def synthesis_node(state: ResearchState):
    return await structured_call(state, "databridge/synthesis", Synthesis)


builder = StateGraph(ResearchState)
builder.add_node("plan", plan_node)
builder.add_node("synthesize", synthesis_node)
builder.add_conditional_edges(
    START, lambda state: state["phase"], {"plan": "plan", "synthesize": "synthesize"}
)
builder.add_edge("plan", END)
builder.add_edge("synthesize", END)
graph = builder.compile()
