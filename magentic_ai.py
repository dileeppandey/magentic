from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from databricks_langchain import ChatDatabricks
from databricks.sdk import WorkspaceClient
import mlflow
import json
from typing import Optional, Any, Generator
import os
import asyncio
from dotenv import load_dotenv
from mlflow.types.agent import ChatAgentMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from mlflow.langchain.chat_agent_langgraph import ChatAgentState
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)
from pydantic import BaseModel
from langchain_core.runnables import RunnableLambda

mlflow.langchain.autolog()
load_dotenv()

# Initialize workspace client and environment variables
w = WorkspaceClient()
os.environ["DATABRICKS_HOST"] = w.config.host
os.environ["DATABRICKS_TOKEN"] = w.tokens.create(comment="for model serving", lifetime_seconds=1200).token_value

# Initialize LLM
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

# Initialize MCP client
client = MultiServerMCPClient({
    "nimble": {
        "url": "https://mcp.nimbleway.com/sse",
        "transport": "sse",
        "headers": {
            "Authorization": f"Bearer {os.getenv('NIMBLE_API_KEY')}"
        }
    }
})

# Agent prompts
flight_agent_prompt = """You are a specialized flight booking assistant for travelers with accessibility needs.
Your goals:
- Always recommend **non-stop round-trip flights**.
- Include **flight numbers, airline names, departure/arrival times, and airports**.
- Include **multiple cabin options** (Economy, Premium Economy, Business) with costs and accessibility benefits.
- Provide details on **wheelchair boarding assistance**, **pre-boarding**, and **in-flight services for accessible travelers**.
- Mention **total cost breakdown** (ticket + taxes + fees).
- Prioritize **morning departures**, **non-stop routes**, and major carriers.
Example output:
- American Airlines Flight 234: Departs BOS at 8:00 AM, arrives SAN at 11:35 AM. Wheelchair assistance available, priority boarding included. Economy: $525, Premium: $745.
ALWAYS USE TOOLS. DO NOT RESPOND DIRECTLY. Give Detailed output. Do not skip anything"""

lodging_agent_prompt = """You are a specialized hotel search assistant for travelers with disabilities.
Your goals:
- Always return **2–3 hotels** with full accessibility.
- Include **room types** (roll-in shower, grab bars, lowered counters, visual fire alarms).
- Include **hotel location** (how far from major landmarks or airports).
- Include **amenities**: elevators, Braille signage, assistive listening devices, accessible pool, ADA shuttles.
- Show **nightly rate**, **total cost**, **star rating**, and **guest accessibility reviews**.
- Emphasize best pick based on **proximity**, **cost**, and **accessibility score**.
Example output:
- Hyatt Regency San Diego: 4-star hotel, 10 min from airport, $225/night. Features include roll-in showers, elevators, hearing aids, and ADA shuttles.
ALWAYS USE TOOLS. DO NOT RESPOND DIRECTLY.  Give Detailed output. Do no skip anything."""

# Initialize module-level variables
tools = None
flight_agent = None
lodging_agent = None
AGENT = None

# Agent descriptions and configuration
flight_agent_description = (
    "The flight agent will fetch all flight information for you. Always ask for information considering asking person is either accessible or disable person.",
)
lodging_agent_description = (
    "The lodging agent will fetch all lodging or hotel information for you. Always ask for information considering asking person is either accessible or disable person.",
)

MAX_ITERATIONS = 6

worker_descriptions = {
    "Flight-Agent": flight_agent_description,
    "Lodging-Agent": lodging_agent_description,
}

formatted_descriptions = "\n".join(
    f"- {name}: {desc}" for name, desc in worker_descriptions.items()
)

system_prompt = f"""You are a Supervisor AI Agent responsible for routing user travel-related requests to the correct specialized sub-agent, with a primary focus on accessibility.
Always assume that the person making the request may have a disability or require accessible accommodations. Your top priority is to ensure accessibility-first results, whether related to flights, hotels, or travel in general.
You can choose from two sub-agents:
Flying Agent – Handles:
- Booking flights
- Checking flight prices or schedules
- Finding best airfare deals
- Flight-related travel questions
Hotel Agent – Handles:
- Booking hotels
- Checking hotel prices or availability
- Finding accommodations
- Hotel-related travel questions
Your job is to:
- Interpret the user's request.
- Decide which agent (Flying Agent or Hotel Agent) is best suited to handle it.
- If both agents are needed, clearly split the request and send parts to the appropriate agents.
- Always prioritize the most accessible options (wheelchair-friendly, visual/auditory aids, proximity to elevators, etc.).
- If the request is unclear or not relevant to either, ask the user for clarification.
Decide between routing between the following workers or ending the conversation if an answer is provided. \n{formatted_descriptions}"""

options = ["FINISH"] + list(worker_descriptions.keys())
FINISH = {"next_node": "FINISH"}

class AgentState(ChatAgentState):
    next_node: str
    iteration_count: int

class LangGraphChatAgent(ChatAgent):
    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        request = {
            "messages": [m.model_dump_compat(exclude_none=True) for m in messages]
        }

        messages = []
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                messages.extend(
                    ChatAgentMessage(**msg) for msg in node_data.get("messages", [])
                )
        return ChatAgentResponse(messages=messages)

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> Generator[ChatAgentChunk, None, None]:
        request = {
            "messages": [m.model_dump_compat(exclude_none=True) for m in messages]
        }
        for event in self.agent.stream(request, stream_mode="updates"):
            for node_data in event.values():
                yield from (
                    ChatAgentChunk(**{"delta": msg})
                    for msg in node_data.get("messages", [])
                )

def parse_next_node(response: str) -> str:
    try:
        data = json.loads(response)
        return data.get("next_node", "FINISH")
    except Exception:
        return "FINISH"

def supervisor_agent(state):
    count = state.get("iteration_count", 0) + 1
    if count > MAX_ITERATIONS:
        return FINISH
    user_msg = next((m["content"] for m in state["messages"] if m["role"] == "user"), "")
    if len(user_msg.strip().split()) < 3:
        return {
            "next_node": "FINISH",
            "messages": [
                {
                    "role": "assistant",
                    "content": "Welcome! I can help with booking **accessible flights and hotels**.\nPlease tell me:\n- Your travel dates\n- Destination\n- Any accessibility needs (e.g., wheelchair assistance)."
                }
            ]
        }
    preprocessor = RunnableLambda(
        lambda state: [{"role": "system", "content": system_prompt}] + state["messages"]
    )
    supervisor_chain = preprocessor | llm | RunnableLambda(
        lambda msg: parse_next_node(
            msg if isinstance(msg, str)
            else msg.content if hasattr(msg, "content")
            else msg[0].content if isinstance(msg, list)
            else ""
        )
    )
    next_node = supervisor_chain.invoke(state)
    if state.get("next_node") == next_node:
        return FINISH
    return {
        "iteration_count": count,
        "next_node": next_node
    }

def agent_node(state, agent, name):
    static_prompts = {
        "Flight-Agent": flight_agent_prompt,
        "Lodging-Agent": lodging_agent_prompt,
    }
    updated_messages = [
        {"role": "system", "content": static_prompts[name]}
    ] + state["messages"]
    result = agent.invoke({"messages": updated_messages})
    return {
        "messages": [
            {
                "role": "assistant",
                "content": result["messages"][-1].content,
                "name": name,
            }
        ]
    }

def final_answer(state):
    prompt = (
        "Summarize the travel plan based on the assistant messages. "
        "Include full details: flight times, prices, assistance available, hotel amenities, accessibility features, and proximity to landmarks. "
        "Use bullet points or sections for readability. Avoid generic tips."
    )
    preprocessor = RunnableLambda(
        lambda state: state["messages"] + [{"role": "user", "content": prompt}]
    )
    final_answer_chain = preprocessor | llm
    return {"messages": [final_answer_chain.invoke(state)]}

async def initialize_agents():
    """Initialize all agents and tools asynchronously"""
    global tools, flight_agent, lodging_agent, AGENT
    
    # Get tools
    tools = await client.get_tools()
    
    # Create agents
    flight_agent = create_react_agent(llm, tools, prompt=flight_agent_prompt)
    lodging_agent = create_react_agent(llm, tools, prompt=lodging_agent_prompt)
    
    # Create and compile workflow
    workflow = StateGraph(AgentState)
    workflow.add_node("Flight-Agent", flight_agent)
    workflow.add_node("Lodging-Agent", lodging_agent)
    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("final_answer", final_answer)
    
    workflow.set_entry_point("supervisor")
    for worker in worker_descriptions.keys():
        workflow.add_edge(worker, "supervisor")
    
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next_node"],
        {**{k: k for k in worker_descriptions.keys()}, "FINISH": "final_answer"},
    )
    workflow.add_edge("final_answer", END)
    
    multi_agent = workflow.compile()
    AGENT = LangGraphChatAgent(multi_agent)

# Initialize agents at module level
asyncio.run(initialize_agents())

def supervisor_agent(messages):
    """Flask-compatible supervisor agent that accepts a list of message dicts"""
    chat_msgs = [ChatAgentMessage(role=m['role'], content=m['content']) for m in messages]
    resp = AGENT.predict(chat_msgs)
    for msg in reversed(resp.messages):
        if msg.role == 'assistant':
            return {'content': msg.content}
    return {'content': resp.messages[-1].content if resp.messages else ""}

# For compatibility with app.py
summary_chain = None
title_agent = None

# --- ASYNC AGENT SETUP ---
import asyncio

# --- Load secrets from .env ---
load_dotenv()
NIMBLE_API_KEY = os.getenv("NIMBLE_API_KEY")
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

async def setup_agents():
    # Use .env secrets if available, otherwise use WorkspaceClient
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        w = WorkspaceClient()
        os.environ["DATABRICKS_HOST"] = w.config.host
        os.environ["DATABRICKS_TOKEN"] = w.tokens.create(comment="for model serving", lifetime_seconds=1200).token_value
    else:
        os.environ["DATABRICKS_HOST"] = DATABRICKS_HOST
        os.environ["DATABRICKS_TOKEN"] = DATABRICKS_TOKEN
    llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
    client = MultiServerMCPClient({
        "nimble": {
            "url": "https://mcp.nimbleway.com/sse",
            "transport": "sse",
            "headers": {"Authorization": f"Bearer {NIMBLE_API_KEY}"}
        }
    })
    tools = await client.get_tools()
    flight_agent_prompt =  """You are a specialized flight booking assistant for travelers with accessibility needs.\nYour goals:\n- Always recommend **non-stop round-trip flights**.\n- Include **flight numbers, airline names, departure/arrival times, and airports**.\n- Include **multiple cabin options** (Economy, Premium Economy, Business) with costs and accessibility benefits.\n- Provide details on **wheelchair boarding assistance**, **pre-boarding**, and **in-flight services for accessible travelers**.\n- Mention **total cost breakdown** (ticket + taxes + fees).\n- Prioritize **morning departures**, **non-stop routes**, and major carriers.\nExample output:\n- American Airlines Flight 234: Departs BOS at 8:00 AM, arrives SAN at 11:35 AM. Wheelchair assistance available, priority boarding included. Economy: $525, Premium: $745.\nALWAYS USE TOOLS. DO NOT RESPOND DIRECTLY. Give Detailed output. Do not skip anything\n    """
    lodging_agent_prompt =  """You are a specialized hotel search assistant for travelers with disabilities.\nYour goals:\n- Always return **2–3 hotels** with full accessibility.\n- Include **room types** (roll-in shower, grab bars, lowered counters, visual fire alarms).\n- Include **hotel location** (how far from major landmarks or airports).\n- Include **amenities**: elevators, Braille signage, assistive listening devices, accessible pool, ADA shuttles.\n- Show **nightly rate**, **total cost**, **star rating**, and **guest accessibility reviews**.\n- Emphasize best pick based on **proximity**, **cost**, and **accessibility score**.\nExample output:\n- Hyatt Regency San Diego: 4-star hotel, 10 min from airport, $225/night. Features include roll-in showers, elevators, hearing aids, and ADA shuttles.\nALWAYS USE TOOLS. DO NOT RESPOND DIRECTLY.  Give Detailed output. Do no skip anything.\n    """
    flight_agent = create_react_agent(llm, tools, prompt=flight_agent_prompt)
    lodging_agent = create_react_agent(llm, tools, prompt=lodging_agent_prompt)
    # --- Multi-agent workflow and AGENT setup ---
    # (Copy your multi-agent workflow, supervisor_agent, etc. here, replacing llm, flight_agent, lodging_agent, tools with the local variables)
    # For demonstration, let's just return a dummy AGENT for now
    class DummyAgent:
        def predict(self, messages):
            return type('Resp', (), {'messages': [type('Msg', (), {'role': 'assistant', 'content': 'This is a dummy response.'})()]})()
    AGENT = DummyAgent()
    return AGENT

AGENT = asyncio.run(setup_agents())

def supervisor_agent(messages):
    chat_msgs = [ChatAgentMessage(role=m['role'], content=m['content']) for m in messages]
    resp = AGENT.predict(chat_msgs)
    for msg in reversed(resp.messages):
        if msg.role == 'assistant':
            return {'content': msg.content}
    return {'content': resp.messages[-1].content if resp.messages else ""}

summary_chain = None
title_agent = None

